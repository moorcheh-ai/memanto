"""
The ``/api/v2`` routes when the server runs on Memanto Cloud.

Same paths, request bodies and response models as the local routes in
``sessions.py`` and ``memory.py``, so the VS Code and Obsidian extensions, the
SDKs and any REST caller work unchanged. Memories are stored and read on
Memanto Cloud; sessions are local (see ``memanto.app.clients.memanto_cloud``).

Mounted by ``memanto.app.main`` instead of the local routes when
``MEMANTO_SERVE_CLOUD=1``.
"""

import asyncio
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)

from memanto.app.clients.memanto_cloud import cloud_client, cloud_http_error
from memanto.app.config import settings
from memanto.app.core import agent_namespace
from memanto.app.models import (
    AnswerRequest,
    AnswerResponse,
    BatchRememberRequest,
    BatchRememberResponse,
    ConflictResolveRequest,
    ExtractMemoriesRequest,
    RecallResponse,
    RememberRequest,
    RememberResponse,
    TemporalRecallResponse,
    UploadFileResponse,
)
from memanto.app.models.session import (
    AgentCreate,
    AgentInfo,
    AgentList,
    AgentPattern,
    Session,
)
from memanto.app.routes import sessions as local_sessions
from memanto.app.routes.auth_deps import (
    get_current_session,
    get_session_service,
    set_session_cookie,
    verify_moorcheh_api_key,
)
from memanto.app.routes.memory import (
    ConflictDetectRequest,
    DailySummaryRequest,
    MemoryEditRequest,
    MemoryExpireRequest,
    PolicyApplyRequest,
    PolicyPresetRequest,
    RecallAsOfRequest,
    RecallChangedSinceRequest,
    RecallRecentRequest,
    RecallRequest,
    _validate_summary_key,
    enforce_session_scope,
    get_policy_preset,
    list_policy_presets,
    resolve_recall_limit,
)
from memanto.app.utils.client_identity import (
    bind_calling_tool,
    detect_client,
    project_name,
    project_tag,
    tool_from_source,
)
from memanto.app.utils.temporal_helpers import utc_date_str
from memanto.app.utils.validation import CostGuard
from memanto.cli.client.hosted_client import (
    _caller,
    _compact,
    _plain_memories,
)
from memanto.cli.config.manager import MEMANTO_CONSOLE_URL, ConfigManager

router = APIRouter()
agent_router = APIRouter()

_config_manager = ConfigManager()

T = TypeVar("T")


async def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking Memanto Cloud call off the event loop, mapping its errors."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as e:
        raise cloud_http_error(e) from e


def _agent_info(agent: dict[str, Any]) -> AgentInfo:
    """A Memanto Cloud agent in the local ``AgentInfo`` shape.

    Memanto Cloud has no namespaces. ``namespace`` is the name a local
    session gives the agent, so agent listings and session responses agree.
    """
    try:
        pattern = AgentPattern(agent.get("pattern") or AgentPattern.SUPPORT)
    except ValueError:
        pattern = AgentPattern.SUPPORT
    return AgentInfo(
        agent_id=agent["agent_id"],
        namespace=agent_namespace(agent["agent_id"]),
        pattern=pattern,
        description=agent.get("description"),
        created_at=agent.get("created_at") or datetime.now().astimezone(),
        memory_count=int(agent.get("memory_count") or 0),
        status=str(agent.get("status") or "ready"),
    )


def _project_tag_for_request() -> str | None:
    """``project_<name>`` for the project the caller named, if it named one.

    Over HTTP the server's working directory says nothing about the caller,
    so only an ``X-Memanto-Project`` header (bound by the server middleware)
    yields a project tag.
    """
    project_dir = detect_client().project_dir
    return project_tag(project_name(project_dir)) if project_dir else None


def _with_request_project_tag(tags: list[str] | None) -> list[str]:
    tags = list(tags or [])
    tag = _project_tag_for_request()
    if tag and tag not in tags and len(tags) < 20:
        tags.append(tag)
    return tags


def _recall_min_similarity(value: float | None) -> float | None:
    if value is not None:
        return value
    configured = _config_manager.get_recall_config().get("min_similarity")
    return None if configured is None else float(configured)


# ============================================================================
# AGENTS AND SESSIONS
# ============================================================================


@router.post("/agents", response_model=AgentInfo, status_code=201)
async def create_agent(
    agent_create: AgentCreate, _key: str = Depends(verify_moorcheh_api_key)
):
    """Create an agent on Memanto Cloud."""
    client = cloud_client()
    agent = await _call(
        client.create_agent,
        agent_create.agent_id,
        agent_create.pattern.value,
        agent_create.description,
    )
    return _agent_info(agent)


@router.get("/agents", response_model=AgentList)
async def list_agents(
    include_counts: bool = Query(True),
    _key: str = Depends(verify_moorcheh_api_key),
):
    """List the Memanto Cloud agents this key can use, newest first.

    ``include_counts`` is accepted for compatibility; Memanto Cloud always
    returns each agent's memory count.
    """
    result = await _call(cloud_client().list_agents)
    agents = [_agent_info(a) for a in result.get("agents", [])]
    return AgentList(
        agents=agents, count=len(agents), warnings=result.get("warnings") or []
    )


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(
    agent_id: str,
    include_counts: bool = Query(True),
    _key: str = Depends(verify_moorcheh_api_key),
):
    """Get one Memanto Cloud agent."""
    return _agent_info(await _call(cloud_client().get_agent, agent_id))


@router.delete("/agents/{agent_id}", status_code=200)
async def delete_agent(
    agent_id: str,
    delete_backup_too: bool = Query(False, alias="delete-backup-too"),
    _key: str = Depends(verify_moorcheh_api_key),
):
    """Delete a Memanto Cloud agent and all its memories.

    Memanto Cloud cannot keep memories without their agent, so the caller must
    confirm with ``delete-backup-too=true``.
    """
    if not delete_backup_too:
        raise HTTPException(
            status_code=400,
            detail=(
                "Memanto Cloud deletes an agent's memories together with the "
                "agent; they cannot be kept. Pass delete-backup-too=true."
            ),
        )
    await _call(cloud_client().delete_agent, agent_id, True)
    return {"message": f"Agent '{agent_id}' successfully deleted with all memories"}


def _activate_locked(agent_id: str) -> Session:
    """Check the agent exists on Memanto Cloud, then start a local session."""
    client = cloud_client()
    session_service = get_session_service()
    with session_service.lock_agent_lifecycle(agent_id):
        agent = client.get_agent(agent_id)  # AgentNotFoundError when missing
        pattern = agent.get("pattern")
        return session_service.create_session(
            agent_id=agent_id,
            pattern=AgentPattern(pattern) if pattern else None,
            duration_hours=settings.SESSION_DEFAULT_DURATION_HOURS,
        )


@router.post("/agents/{agent_id}/activate", response_model=Session)
async def activate_agent(
    agent_id: str,
    request: Request,
    response: Response,
    _key: str = Depends(verify_moorcheh_api_key),
):
    """Activate a Memanto Cloud agent: a local session, as the CLI keeps one."""
    session = await _call(_activate_locked, agent_id)
    set_session_cookie(response, session.session_token, request)
    return session


# Deactivate and status only touch local session state: reuse them as they are.
router.add_api_route(
    "/agents/{agent_id}/deactivate",
    local_sessions.deactivate_agent,
    methods=["POST"],
    response_model=local_sessions.SessionSummary,
)
router.add_api_route(
    "/status",
    local_sessions.get_status,
    methods=["GET"],
    response_model=local_sessions.SessionInfo,
)


# ============================================================================
# MEMORY OPERATIONS (mounted under /agents)
# ============================================================================


@agent_router.post("/{agent_id}/remember", response_model=RememberResponse)
async def remember(
    agent_id: str,
    request: RememberRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Store one memory on Memanto Cloud."""
    CostGuard.validate_text_length(request.content, "Memory content")
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    client = cloud_client(session)
    result = await _call(
        client._request,
        "POST",
        client._agent_path(agent_id, "/remember"),
        json=_compact(
            {
                "type": request.type,
                "title": request.title,
                "content": request.content,
                "confidence": request.confidence,
                "tags": _with_request_project_tag(request.tags),
                "source": request.source,
                "provenance": request.provenance,
            }
        ),
    )
    return {
        "memory_id": result.get("memory_id"),
        "agent_id": agent_id,
        "session_id": session.session_id,
        "namespace": session.namespace,
        "status": result.get("status", "queued"),
        "provenance": result.get("provenance", request.provenance),
        "confidence": result.get("confidence", request.confidence),
        "type": result.get("type"),
    }


@agent_router.post("/{agent_id}/batch-remember", response_model=BatchRememberResponse)
async def batch_remember(
    agent_id: str,
    request: BatchRememberRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Store up to 100 memories on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    for item in request.memories:
        CostGuard.validate_text_length(item.content, "Memory content")
    memories = [
        item.model_dump(mode="json", exclude_none=True) for item in request.memories
    ]
    result = await _call(
        cloud_client(session).batch_remember, agent_id, memories, request.source
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "namespace": session.namespace,
        "total_submitted": result.get("total_submitted", len(memories)),
        "successful": result.get("successful", 0),
        "failed": result.get("failed", 0),
        "results": result.get("results", []),
    }


@agent_router.patch("/{agent_id}/memories/{memory_id}")
async def edit_memory(
    agent_id: str,
    memory_id: str,
    request: MemoryEditRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Update fields of one memory on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    updates = request.to_updates()
    if not updates:
        raise HTTPException(
            status_code=400, detail="Provide at least one field to update."
        )
    if "content" in updates:
        CostGuard.validate_text_length(str(updates["content"]), "Memory content")
    result = await _call(
        cloud_client(session).update_memory, agent_id, memory_id, updates
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "namespace": session.namespace,
        "memory_id": memory_id,
        "status": result.get("status", "updated"),
        "action": result.get("action", "updated"),
        "updated_fields": result.get("updated_fields", list(updates.keys())),
    }


@agent_router.post("/{agent_id}/remember/extract")
async def extract_memories_from_conversation(
    agent_id: str,
    request: ExtractMemoriesRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Extract typed memories from a conversation on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    result = await _call(
        cloud_client(session).extract_memories_from_conversation,
        agent_id,
        [m.model_dump(mode="json") for m in request.messages],
        request.dry_run,
        request.max_memories,
        request.ai_model,
        request.source,
    )
    return {**result, "agent_id": agent_id, "session_id": session.session_id}


@agent_router.post("/{agent_id}/upload-file", response_model=UploadFileResponse)
async def upload_file(
    agent_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_current_session),
):
    """Upload a file to the agent on Memanto Cloud; it becomes memories."""
    enforce_session_scope(session, agent_id)
    name = Path(file.filename or "upload").name
    if not name or name in (".", ".."):
        name = "upload"
    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_path = Path(tmp_dir) / name
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                await asyncio.to_thread(out.write, chunk)
        result = await _call(cloud_client(session).upload_file, agent_id, str(tmp_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "namespace": session.namespace,
        "file_name": result.get("file_name", name),
        "file_size": result.get("file_size"),
        "status": "uploaded" if result.get("success") else "failed",
        "message": result.get("message", ""),
    }


@agent_router.delete("/{agent_id}/memories/{memory_id}")
async def delete_memory(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
):
    """Permanently delete one memory on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    await _call(cloud_client(session).delete_memory, agent_id, memory_id)
    return {
        "agent_id": agent_id,
        "memory_id": memory_id,
        "namespace": session.namespace,
        "status": "deleted",
    }


@agent_router.post("/{agent_id}/recall", response_model=RecallResponse)
async def recall(
    agent_id: str,
    req: RecallRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Semantic recall on Memanto Cloud."""
    CostGuard.validate_query_length(req.query)
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(req.source))
    result = await _call(
        cloud_client(session).recall,
        agent_id,
        req.query,
        limit=resolve_recall_limit(req.limit),
        type=req.type,
        tags=req.tags,
        min_similarity=_recall_min_similarity(req.min_similarity),
        created_after=req.created_after,
        created_before=req.created_before,
        status=req.status,
        source=req.source,
    )
    memories = result.get("memories", [])
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "query": req.query,
        "memories": memories,
        "count": len(memories),
    }


@agent_router.post("/{agent_id}/answer", response_model=AnswerResponse)
async def answer(
    agent_id: str,
    request: AnswerRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Answer a question from the agent's memories on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    result = await _call(
        cloud_client(session).answer,
        agent_id,
        request.question,
        limit=request.limit,
        threshold=request.threshold,
        temperature=request.temperature,
        ai_model=request.ai_model,
        kiosk_mode=request.kiosk_mode,
        source=request.source,
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "question": request.question,
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "namespace": session.namespace,
    }


@agent_router.post("/{agent_id}/daily-summary")
async def generate_daily_summary(
    agent_id: str,
    request: DailySummaryRequest = Body(default_factory=DailySummaryRequest),
    session: Session = Depends(get_current_session),
):
    """Generate and store one day's summary on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    resolved_date = request.date or utc_date_str()
    _validate_summary_key(agent_id, resolved_date)
    client = cloud_client(session)
    result = await _call(
        client._request,
        "POST",
        client._agent_path(agent_id, "/daily-summary"),
        json={"date": resolved_date},
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "date": resolved_date,
        "summary": result.get("summary", {}),
    }


@agent_router.post("/{agent_id}/conflicts/generate")
async def generate_conflict_report(
    agent_id: str,
    request: ConflictDetectRequest = Body(default_factory=ConflictDetectRequest),
    session: Session = Depends(get_current_session),
):
    """Scan one day's memories for conflicts on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    resolved_date = request.date or utc_date_str()
    _validate_summary_key(agent_id, resolved_date)
    result = await _call(
        cloud_client(session).generate_conflict_report, agent_id, resolved_date
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "date": resolved_date,
        **result,
    }


@agent_router.get("/{agent_id}/conflicts")
async def list_conflicts(
    agent_id: str,
    date: str | None = Query(None),
    session: Session = Depends(get_current_session),
):
    """Unresolved conflicts for one day on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    resolved_date = date or utc_date_str()
    _validate_summary_key(agent_id, resolved_date)
    conflicts = await _call(
        cloud_client(session).list_conflicts, agent_id, resolved_date
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "date": resolved_date,
        "conflicts": conflicts,
        "count": len(conflicts),
    }


@agent_router.post("/{agent_id}/conflicts/resolve")
async def resolve_conflict(
    agent_id: str,
    request: ConflictResolveRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Resolve one conflict by its index on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    resolved_date = request.date or utc_date_str()
    _validate_summary_key(agent_id, resolved_date)
    result = await _call(
        cloud_client(session).resolve_conflict,
        agent_id,
        resolved_date,
        request.conflict_index,
        request.action,
        request.manual_content,
        request.manual_type,
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "date": resolved_date,
        **result,
    }


async def _temporal(
    session: Session, agent_id: str, route: str, body: dict[str, Any]
) -> dict[str, Any]:
    client = cloud_client(session)
    result = await _call(
        client._request,
        "POST",
        client._agent_path(agent_id, f"/recall/{route}"),
        json=_compact(body),
    )
    memories = _plain_memories(result)
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "memories": memories,
        "count": len(memories),
    }


@agent_router.post("/{agent_id}/recall/as-of", response_model=TemporalRecallResponse)
async def recall_as_of(
    agent_id: str,
    request: RecallAsOfRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """What the agent knew at a point in time, on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    result = await _temporal(
        session,
        agent_id,
        "as-of",
        {
            "as_of": request.as_of.isoformat(),
            "limit": resolve_recall_limit(request.limit),
            "type": request.type,
            "tags": request.tags,
            "source": _caller(request.source),
        },
    )
    return {
        **result,
        "as_of_date": request.as_of.isoformat(),
        "temporal_mode": "as_of",
    }


@agent_router.post(
    "/{agent_id}/recall/changed-since", response_model=TemporalRecallResponse
)
async def recall_changed_since(
    agent_id: str,
    request: RecallChangedSinceRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Memories created or changed since a time, on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    result = await _temporal(
        session,
        agent_id,
        "changed-since",
        {
            "since": request.since.isoformat(),
            "limit": resolve_recall_limit(request.limit),
            "type": request.type,
            "tags": request.tags,
            "status": request.status,
            "source": _caller(request.source),
        },
    )
    return {
        **result,
        "since_date": request.since.isoformat(),
        "temporal_mode": "changed_since",
    }


@agent_router.post("/{agent_id}/recall/recent", response_model=TemporalRecallResponse)
async def recall_recent(
    agent_id: str,
    request: RecallRecentRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """The newest memories, on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    bind_calling_tool(tool_from_source(request.source))
    if request.created_after or request.created_before:
        raise HTTPException(
            status_code=400,
            detail="created_after / created_before are not available on Memanto Cloud.",
        )
    result = await _temporal(
        session,
        agent_id,
        "recent",
        {
            "limit": resolve_recall_limit(request.limit),
            "type": request.type,
            "tags": request.tags,
            "status": request.status,
            "source": _caller(request.source),
        },
    )
    return {**result, "temporal_mode": "recent"}


@agent_router.post("/{agent_id}/recall/all", response_model=TemporalRecallResponse)
async def recall_all(agent_id: str):
    """Not available on Memanto Cloud."""
    raise HTTPException(
        status_code=501,
        detail="recall/all is not available on Memanto Cloud. Use recall/recent.",
    )


@agent_router.post("/{agent_id}/memories/{memory_id}/expire")
async def expire_memory(
    agent_id: str,
    memory_id: str,
    request: MemoryExpireRequest = Body(default=MemoryExpireRequest()),
    session: Session = Depends(get_current_session),
):
    """Mark one memory expired on Memanto Cloud (reversible)."""
    enforce_session_scope(session, agent_id)
    result = await _call(
        cloud_client(session).expire_memory, agent_id, memory_id, request.reason
    )
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "memory_id": memory_id,
        "status": "expired",
        "expired_at": result.get("expired_at"),
        "expired_by": result.get("expired_by"),
    }


@agent_router.post("/{agent_id}/memories/{memory_id}/restore")
async def restore_memory(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
):
    """Return an expired memory to active on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    await _call(cloud_client(session).restore_memory, agent_id, memory_id)
    return {
        "agent_id": agent_id,
        "session_id": session.session_id,
        "memory_id": memory_id,
        "status": "active",
    }


@agent_router.get("/{agent_id}/policy")
async def get_policy(agent_id: str, session: Session = Depends(get_current_session)):
    """The agent's expiry policy on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    return await _call(cloud_client(session).get_policy, agent_id)


@agent_router.put("/{agent_id}/policy")
async def set_policy(
    agent_id: str,
    policy: dict[str, Any] = Body(...),
    session: Session = Depends(get_current_session),
):
    """Replace the agent's expiry policy on Memanto Cloud."""
    from memanto.app.services.memory_policy_service import MemoryPolicy

    enforce_session_scope(session, agent_id)
    try:
        validated = MemoryPolicy.model_validate(policy)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await _call(
        cloud_client(session).set_policy,
        agent_id,
        validated.model_dump(mode="json", exclude_none=True),
    )


# The presets are the same predefined bundles locally and on Memanto Cloud.
agent_router.add_api_route(
    "/{agent_id}/policy/presets", list_policy_presets, methods=["GET"]
)
agent_router.add_api_route(
    "/{agent_id}/policy/presets/{name}", get_policy_preset, methods=["GET"]
)


@agent_router.post("/{agent_id}/policy/preset")
async def apply_policy_preset(
    agent_id: str,
    request: PolicyPresetRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """Replace the agent's policy with a preset on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    return await _call(
        cloud_client(session).apply_policy_preset, agent_id, request.name
    )


@agent_router.post("/{agent_id}/policy/apply")
async def apply_policy(
    agent_id: str,
    request: PolicyApplyRequest = Body(default=PolicyApplyRequest()),
    session: Session = Depends(get_current_session),
):
    """Expire every memory the policy matches, on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    return await _call(cloud_client(session).apply_policy, agent_id, request.dry_run)


@agent_router.post("/{agent_id}/policy/purge")
async def purge_expired_memories(
    agent_id: str,
    request: PolicyApplyRequest = Body(default=PolicyApplyRequest()),
    session: Session = Depends(get_current_session),
):
    """Permanently delete memories expired past the purge window, on Memanto Cloud."""
    enforce_session_scope(session, agent_id)
    return await _call(cloud_client(session).purge_expired, agent_id, request.dry_run)


router.include_router(agent_router, prefix="/agents", tags=["Memory Operations"])


# ============================================================================
# WEB UI
# ============================================================================

ui_router = APIRouter()


@ui_router.get("/ui", include_in_schema=False)
@ui_router.get("/ui/{path:path}", include_in_schema=False)
async def ui_on_cloud(path: str = ""):
    """The local dashboard reads Memanto local; on Memanto Cloud, use the console."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"{MEMANTO_CONSOLE_URL}/memory", status_code=307)

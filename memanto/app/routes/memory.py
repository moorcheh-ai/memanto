"""
Memory Operations - Session-Based

Memory operations using session tokens (no tenant_id).
Replaces legacy agent memory endpoints with session-based auth.
"""

import asyncio
import os
import re
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.config import settings
from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.core import MemoryRecord
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
from memanto.app.models.session import Session
from memanto.app.routes.auth_deps import get_current_session, get_session_service
from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
)
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import AuthorizationError, map_error_to_http_exception
from memanto.app.utils.validation import CostGuard, validate_safe_id
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.config.manager import ConfigManager

router = APIRouter()

_config_manager = ConfigManager()
_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_summary_key(agent_id: str, date_str: str) -> None:
    """Reject identifiers that are unsafe for summary/conflict file paths."""
    if not _SAFE_DATE_RE.fullmatch(date_str):
        raise HTTPException(status_code=400, detail="Invalid summary identifier")
    try:
        validate_safe_id(agent_id, "agent_id")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid summary identifier")


class RecallRequest(BaseModel):
    """Request body for semantic memory recall."""

    query: str = Field(..., min_length=1, description="Search query")
    limit: int | None = Field(default=None, ge=1, description="Max results")
    min_similarity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score (0-1)"
    )
    type: list[str] | None = Field(default=None, description="Memory type filters")


class RecallAsOfRequest(BaseModel):
    """Request body for point-in-time memory recall."""

    as_of: datetime = Field(
        ...,
        description="Point-in-time — YYYY-MM-DD (defaults to end of day) or full ISO datetime e.g. 2025-11-01T14:30:00Z",
    )
    limit: int | None = Field(default=None, ge=1, description="Max results")
    type: list[str] | None = Field(default=None, description="Memory type filters")

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_as_of(cls, v: object) -> datetime:
        """Parse date-only or ISO datetime inputs into an aware timestamp."""
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, date):
            return datetime.combine(v, time(23, 59, 59), tzinfo=timezone.utc)
        if isinstance(v, str):
            # Date-only (no time component) → end of day
            if "T" not in v and " " not in v:
                try:
                    return datetime.combine(
                        date.fromisoformat(v), time(23, 59, 59), tzinfo=timezone.utc
                    )
                except ValueError:
                    pass
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(
                    f"Invalid value '{v}'. Use YYYY-MM-DD or ISO 8601 datetime."
                )
        raise ValueError(f"Cannot parse as_of from {type(v)}")


class RecallChangedSinceRequest(BaseModel):
    """Request body for querying memories changed since a timestamp."""

    since: datetime = Field(
        ...,
        description="Start of change window — YYYY-MM-DD (defaults to start of day) or full ISO datetime e.g. 2025-11-01T00:00:00Z",
    )
    limit: int | None = Field(default=None, ge=1, description="Max results")
    type: list[str] | None = Field(default=None, description="Memory type filters")

    @field_validator("since", mode="before")
    @classmethod
    def parse_since(cls, v: object) -> datetime:
        """Parse date-only or ISO datetime inputs for change filtering."""
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, date):
            return datetime.combine(v, time(0, 0, 0), tzinfo=timezone.utc)
        if isinstance(v, str):
            # Date-only (no time component) → start of day
            if "T" not in v and " " not in v:
                try:
                    return datetime.combine(
                        date.fromisoformat(v), time(0, 0, 0), tzinfo=timezone.utc
                    )
                except ValueError:
                    pass
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(
                    f"Invalid value '{v}'. Use YYYY-MM-DD or ISO 8601 datetime."
                )
        raise ValueError(f"Cannot parse since from {type(v)}")


class RecallRecentRequest(BaseModel):
    """Request body for retrieving recent memories."""

    limit: int | None = Field(default=None, ge=1, description="Max results")
    type: list[str] | None = Field(default=None, description="Memory type filters")


class MemoryEditRequest(BaseModel):
    """Request body for partial memory record updates."""

    title: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, max_length=10000)
    type: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    source: str | None = None

    def to_updates(self) -> dict[str, object]:
        """Return only fields the caller explicitly wants to update."""
        return self.model_dump(exclude_none=True)


def enforce_session_scope(session: Session, agent_id: str) -> None:
    """Ensure a session can only access the agent scope it was issued for."""
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            AuthorizationError(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )


@router.post("/{agent_id}/remember", response_model=RememberResponse)
async def remember(
    agent_id: str,
    request: RememberRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Store a memory (Session-based)

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.

    Provenance types:
    - explicit_statement: Directly stated by user
    - inferred: Derived from behavior/context
    - observed: Seen in action
    - validated: Confirmed/verified
    - corrected: Updated after contradiction
    - imported: From external source
    """
    CostGuard.validate_text_length(request.content, "Memory content")

    # Enforce session scope: token must match agent_id
    enforce_session_scope(session, agent_id)

    try:
        # Initialize memory write service
        write_service = MemoryWriteService(client)

        from typing import cast

        from memanto.app.constants import MemoryType, ProvenanceType

        resolved_title = request.title or (
            f"{request.content[:50]}..."
            if len(request.content) > 50
            else request.content
        )

        # Create memory record with scope fields and provenance
        memory = MemoryRecord(
            type=cast(MemoryType, request.type),
            title=resolved_title,
            content=request.content,
            agent_id=agent_id,
            actor_id=agent_id,
            confidence=request.confidence,
            tags=request.tags or [],
            source=request.source,
            provenance=cast(ProvenanceType, request.provenance),
        )

        # Store memory in agent's namespace.
        result = await asyncio.to_thread(write_service.store_memory, memory)

        # Log to local session Markdown summary
        session_service = get_session_service()
        await asyncio.to_thread(
            session_service.log_memory_to_session_summary,
            agent_id=agent_id,
            session_id=session.session_id,
            memory_record=memory,
        )

        return {
            "memory_id": result["id"],
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": session.namespace,
            "status": "queued",
            "provenance": request.provenance,
            "confidence": request.confidence,
            # Resolved memory type (auto-parsed when not explicitly provided)
            "type": result.get("type"),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/batch-remember", response_model=BatchRememberResponse)
async def batch_remember(
    agent_id: str,
    request: BatchRememberRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Store multiple memories in batch (Session-based)

    Accepts up to 100 memories per request. Leverages Moorcheh's batch
    upload capability for efficient storage.

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope: token must match agent_id
    enforce_session_scope(session, agent_id)

    try:
        # Initialize memory write service
        write_service = MemoryWriteService(client)

        # Convert each item to a MemoryRecord
        from typing import cast

        from memanto.app.constants import MemoryType, ProvenanceType

        memory_records = []
        for item in request.memories:
            title = item.title or (
                item.content[:47] + "..." if len(item.content) > 50 else item.content
            )
            memory = MemoryRecord(
                type=cast(MemoryType, item.type),
                title=title,
                content=item.content,
                agent_id=agent_id,
                actor_id=agent_id,
                confidence=item.confidence,
                tags=item.tags or [],
                source=item.source,
                provenance=cast(ProvenanceType, item.provenance),
            )
            memory_records.append(memory)

        # Store in batch
        result = await asyncio.to_thread(
            write_service.batch_store_memories, memory_records
        )

        # Log each memory to local MD summary
        session_service = get_session_service()

        for record in memory_records:
            await asyncio.to_thread(
                session_service.log_memory_to_session_summary,
                agent_id=agent_id,
                session_id=session.session_id,
                memory_record=record,
            )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": session.namespace,
            "total_submitted": result["total_submitted"],
            "successful": result["successful"],
            "failed": result["failed"],
            "results": result["results"],
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.patch("/{agent_id}/memories/{memory_id}")
async def edit_memory(
    agent_id: str,
    memory_id: str,
    request: MemoryEditRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Update one memory in the active agent's namespace (Session-based).

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    enforce_session_scope(session, agent_id)

    updates = request.to_updates()
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update.",
        )

    if "content" in updates:
        content = updates["content"]
        if content is None or not str(content).strip():
            raise HTTPException(
                status_code=400,
                detail="Memory content must be a non-empty string.",
            )
        CostGuard.validate_text_length(str(content), "Memory content")
    if "confidence" in updates:
        confidence = updates["confidence"]
        try:
            confidence_value = float(confidence)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Confidence must be a number between 0.0 and 1.0, got {confidence!r}.",
            )
        if not 0.0 <= confidence_value <= 1.0:
            raise HTTPException(
                status_code=400,
                detail=f"Confidence must be between 0.0 and 1.0, got {confidence_value}.",
            )
    if "type" in updates and updates["type"] not in VALID_MEMORY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid memory_type '{updates['type']}'. "
                f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}."
            ),
        )

    try:
        write_service = MemoryWriteService(client)
        result = await asyncio.to_thread(
            write_service.update_memory, memory_id, session.namespace, updates
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

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404, detail=f"Memory '{memory_id}' was not found."
            )
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/remember/extract")
async def extract_memories_from_conversation(
    agent_id: str,
    request: ExtractMemoriesRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Extract typed memory candidates from chat-style conversation turns.

    Requires:
    - X-Session-Token: {session_token}

    When dry_run is true, candidates are returned without writing. Otherwise the
    candidates are persisted through the same batch memory path used by
    /batch-remember.
    """
    enforce_session_scope(session, agent_id)

    try:
        extraction_service = ConversationMemoryExtractionService(client)
        candidates = await asyncio.to_thread(
            extraction_service.extract,
            namespace=session.namespace,
            messages=[message.model_dump(mode="json") for message in request.messages],
            max_memories=request.max_memories,
            ai_model=request.ai_model,
        )

        if request.dry_run:
            return {
                "agent_id": agent_id,
                "session_id": session.session_id,
                "dry_run": True,
                "candidates": candidates,
                "count": len(candidates),
            }

        write_service = MemoryWriteService(client)

        from typing import cast

        from memanto.app.constants import MemoryType, ProvenanceType

        memory_records = []
        for item in candidates:
            memory = MemoryRecord(
                type=cast(MemoryType, item.get("type")),
                title=item["title"],
                content=item["content"],
                agent_id=agent_id,
                actor_id=agent_id,
                confidence=item["confidence"],
                tags=["conversation-extract"],
                source=item["source"],
                provenance=cast(ProvenanceType, item["provenance"]),
            )
            memory_records.append(memory)

        result = await asyncio.to_thread(
            write_service.batch_store_memories, memory_records
        )

        session_service = get_session_service()
        for index, record in enumerate(memory_records):
            batch_results = result.get("results", [])
            memory_id = (
                batch_results[index].get("id") if index < len(batch_results) else None
            )
            await asyncio.to_thread(
                session_service.log_memory_to_session_summary,
                agent_id=agent_id,
                session_id=session.session_id,
                memory_record=record,
                memory_id=memory_id,
            )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "dry_run": False,
            "candidates": candidates,
            "total_submitted": result["total_submitted"],
            "successful": result["successful"],
            "failed": result["failed"],
            "results": result["results"],
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/upload-file", response_model=UploadFileResponse)
async def upload_file(
    agent_id: str,
    file: UploadFile = File(
        ..., description="File to upload (.pdf, .docx, .xlsx, .json, .txt, .csv, .md)"
    ),
    session: Session = Depends(get_current_session),
):
    """
    Upload a file directly to the agent's memory namespace (Session-based)

    Supported formats: .pdf, .docx, .xlsx, .json, .txt, .csv, .md
    Maximum file size: 5GB

    The file is processed by Moorcheh to extract text and generate embeddings,
    making its content searchable via recall.

    Requires:
    - X-Session-Token: {session_token}
    - Content-Type: multipart/form-data
    """
    enforce_session_scope(session, agent_id)

    client = get_moorcheh_client()

    # Validate file extension before reading
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".json", ".txt", ".csv", ".md"}
    # Sanitize filename: strip directory components to prevent path traversal (CWE-22)
    original_name = Path(file.filename or "upload").name
    # Guard against empty or dot-only filenames after sanitization
    if not original_name or original_name in (".", ".."):
        original_name = "upload"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not supported. Allowed types: {allowed_str}",
        )

    try:
        namespace = session.namespace

        # Write upload to a temp file so moorcheh SDK can read it
        # Use original filename so the SDK records it as the source
        file_bytes = await file.read()
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, original_name)
        # Defense-in-depth: verify resolved path is within tmp_dir
        if not os.path.realpath(tmp_path).startswith(
            os.path.realpath(tmp_dir) + os.sep
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename",
            )
        try:
            with open(tmp_path, "wb") as tmp:
                tmp.write(file_bytes)
            result = await asyncio.to_thread(
                client.documents.upload_file, namespace, tmp_path
            )
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": namespace,
            "file_name": original_name,
            "file_size": result.get("fileSize"),
            "status": "uploaded" if result.get("success") else "failed",
            "message": result.get("message", ""),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.delete("/{agent_id}/memories/{memory_id}")
async def delete_memory(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Delete one memory from the active agent namespace.

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    enforce_session_scope(session, agent_id)

    try:
        write_service = MemoryWriteService(client)
        deleted = await asyncio.to_thread(
            write_service.delete_memory,
            memory_id,
            session.namespace,
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Memory '{memory_id}' was not found for agent '{agent_id}'",
            )

        return {
            "agent_id": agent_id,
            "memory_id": memory_id,
            "namespace": session.namespace,
            "status": "deleted",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/recall", response_model=RecallResponse)
async def recall(
    agent_id: str,
    request: RecallRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Recall memories (Session-based)

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    CostGuard.validate_query_length(request.query)

    # Enforce session scope
    enforce_session_scope(session, agent_id)

    recall_cfg = _config_manager.get_recall_config()
    raw_limit = (
        request.limit
        if request.limit is not None
        else recall_cfg.get("limit", settings.RECALL_LIMIT)
    )
    raw_min_similarity = (
        request.min_similarity
        if request.min_similarity is not None
        else recall_cfg.get("min_similarity")
    )
    try:
        limit = int(raw_limit)
        min_similarity = (
            None if raw_min_similarity is None else float(raw_min_similarity)
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid recall configuration: {e}"
        )
    CostGuard.validate_k_limit(limit)

    try:
        # Initialize memory read service
        read_service = MemoryReadService(client)

        # Search in agent's namespace using scope.
        result = await asyncio.to_thread(
            read_service.search_memories,
            query=request.query,
            agent_id=agent_id,
            type=request.type,
            min_similarity_score=min_similarity,
            limit=limit,
        )

        memories = result.get("results", [])

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "query": request.query,
            "memories": memories,
            "count": len(memories),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/answer", response_model=AnswerResponse)
async def answer(
    agent_id: str,
    request: AnswerRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """
    Answer a question using RAG (Session-based)

    Requires:
    - X-Session-Token: {session_token}

    Uses Moorcheh's answer.generate endpoint to produce LLM-generated answers
    based on the agent's stored memories.
    """
    CostGuard.validate_query_length(request.question)

    # Enforce session scope
    enforce_session_scope(session, agent_id)

    client = get_moorcheh_client()

    # Resolve defaults from settings
    limit = request.limit if request.limit is not None else settings.ANSWER_LIMIT
    CostGuard.validate_k_limit(limit)
    temperature = (
        request.temperature
        if request.temperature is not None
        else settings.ANSWER_TEMPERATURE
    )
    ai_model = (
        request.ai_model
        if request.ai_model is not None
        else get_active_llm_model(settings.ANSWER_MODEL)
    )

    try:
        # Use namespace from session
        namespace = session.namespace

        # Internal fixed prompts (not user-configurable via API contract)
        header_prompt = (
            "You are a helpful AI assistant with access to the agent's persistent memory. "
            "Use the provided context from the agent's memories to answer the user's question accurately. "
            "If the memories don't contain relevant information, say so clearly."
        )

        footer_prompt = (
            "Answer the question based on the memory context above. "
            "Be concise and cite specific memories when relevant. "
            "If no relevant memories exist, acknowledge that."
        )

        # Use Moorcheh's answer.generate endpoint. Threshold is required
        # when kiosk_mode is on — fall back to 0.15 when the caller did
        # not specify one.
        generate_kwargs = {
            "namespace": namespace,
            "query": request.question,
            "top_k": limit,
            "temperature": temperature,
            "ai_model": ai_model,
            "kiosk_mode": request.kiosk_mode,
            "header_prompt": header_prompt,
            "footer_prompt": footer_prompt,
        }
        if request.kiosk_mode:
            generate_kwargs["threshold"] = (
                request.threshold if request.threshold is not None else 0.15
            )

        response = await asyncio.to_thread(client.answer.generate, **generate_kwargs)

        # Extract the generated answer and sources
        answer = response.get("answer", "No answer generated.")
        sources = response.get("sources", [])

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "question": request.question,
            "answer": answer,
            "sources": sources,
            "namespace": namespace,
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


class DailySummaryRequest(BaseModel):
    """Request body for on-demand daily summary generation."""

    date: str | None = Field(
        default=None,
        description="Date string YYYY-MM-DD. Defaults to today.",
    )
    output_path: str | None = Field(
        default=None,
        description=(
            "Accepted for backwards compatibility but ignored; summaries use "
            "the server-controlled output location."
        ),
    )


class ConflictDetectRequest(BaseModel):
    """Request body for on-demand conflict report generation."""

    date: str | None = Field(
        default=None,
        description="Date string YYYY-MM-DD. Defaults to today.",
    )


@router.post("/{agent_id}/daily-summary")
async def generate_daily_summary(
    agent_id: str,
    request: DailySummaryRequest = Body(default_factory=DailySummaryRequest),
    session: Session = Depends(get_current_session),
):
    """
    Generate the on-demand daily AI summary for an agent/date.

    Conflict detection is a separate concern — see
    POST ``/{agent_id}/conflicts/generate`` or the scheduled job.
    """
    enforce_session_scope(session, agent_id)

    resolved_date = request.date or datetime.now().strftime("%Y-%m-%d")
    _validate_summary_key(agent_id, resolved_date)
    try:
        result = await asyncio.to_thread(
            DirectClient(settings.MOORCHEH_API_KEY).generate_daily_summary,
            agent_id,
            resolved_date,
            None,
        )
        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "date": resolved_date,
            **result,
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/conflicts/generate")
async def generate_conflict_report(
    agent_id: str,
    request: ConflictDetectRequest = Body(default_factory=ConflictDetectRequest),
    session: Session = Depends(get_current_session),
):
    """
    Generate the conflict report for an agent/date.

    This is the same work the scheduled task performs.
    """
    enforce_session_scope(session, agent_id)

    resolved_date = request.date or datetime.now().strftime("%Y-%m-%d")
    _validate_summary_key(agent_id, resolved_date)
    try:
        result = await asyncio.to_thread(
            DirectClient(settings.MOORCHEH_API_KEY).generate_conflict_report,
            agent_id,
            resolved_date,
        )
        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "date": resolved_date,
            **result,
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/conflicts")
async def list_conflicts(
    agent_id: str,
    date: str | None = Query(None, description="Conflict report date (YYYY-MM-DD)"),
    session: Session = Depends(get_current_session),
):
    """
    List unresolved conflicts for an agent.

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope
    enforce_session_scope(session, agent_id)

    resolved_date = date or datetime.now().strftime("%Y-%m-%d")
    _validate_summary_key(agent_id, resolved_date)
    try:
        conflicts = await asyncio.to_thread(
            DirectClient(settings.MOORCHEH_API_KEY).list_conflicts,
            agent_id,
            resolved_date,
        )
        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "date": resolved_date,
            "conflicts": conflicts,
            "count": len(conflicts),
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/conflicts/resolve")
async def resolve_conflict(
    agent_id: str,
    request: ConflictResolveRequest = Body(...),
    session: Session = Depends(get_current_session),
):
    """
    Resolve a conflict for an agent.

    Uses the same underlying conflict resolution service used by CLI.
    """
    enforce_session_scope(session, agent_id)

    resolved_date = request.date or datetime.now().strftime("%Y-%m-%d")
    _validate_summary_key(agent_id, resolved_date)
    try:
        result = await asyncio.to_thread(
            DirectClient(settings.MOORCHEH_API_KEY).resolve_conflict,
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

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/recall/as-of", response_model=TemporalRecallResponse)
async def recall_as_of(
    agent_id: str,
    request: RecallAsOfRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Point-in-time recall: "What was true at this point in time?"

    Returns memories stored before the specified datetime, excluding memories
    created after or expired before as_of.

    Example: "What memories did we have on 2025-11-01?"

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    # request.limit is None → fetch all (no cap). Cost guard only applies when capped.
    limit = request.limit
    if limit is not None:
        CostGuard.validate_k_limit(limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_as_of,
            as_of_date=request.as_of.isoformat(),
            agent_id=agent_id,
            type=request.type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "as_of_date": request.as_of.isoformat(),
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "as_of",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/recall/changed-since", response_model=TemporalRecallResponse)
async def recall_changed_since(
    agent_id: str,
    request: RecallChangedSinceRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Differential retrieval: "What changed recently?"

    Returns memories created or updated after the specified datetime.

    Example: "What changed since last week?"

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    # request.limit is None → fetch all (no cap). Cost guard only applies when capped.
    limit = request.limit
    if limit is not None:
        CostGuard.validate_k_limit(limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_changed_since,
            since_date=request.since.isoformat(),
            agent_id=agent_id,
            type=request.type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "since_date": request.since.isoformat(),
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "changed_since",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/recall/recent", response_model=TemporalRecallResponse)
async def recall_recent(
    agent_id: str,
    request: RecallRecentRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Recall the most recently stored memories.

    Returns memories sorted by created_at descending (newest first).
    Optionally filter by memory type.

    Requires:
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    enforce_session_scope(session, agent_id)

    # request.limit is None → fetch all (no cap). Cost guard only applies when capped.
    limit = request.limit
    if limit is not None:
        CostGuard.validate_k_limit(limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_recent,
            agent_id=agent_id,
            type=request.type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "recent",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)

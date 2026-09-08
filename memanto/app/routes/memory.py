"""
Memory Operations - Session-Based

Memory operations using session tokens (no tenant_id).
Replaces legacy agent memory endpoints with session-based auth.
"""

import asyncio
import logging
import os
import re
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator

from memanto.app.clients.backend import get_active_llm_model
from memanto.app.clients.moorcheh import (
    get_server_moorcheh_client,
)
from memanto.app.config import settings
from memanto.app.constants import VALID_MEMORY_TYPES, MemoryType, StatusFilter
from memanto.app.core import MemoryRecord, MemorySource
from memanto.app.models import (
    AnswerRequest,
    AnswerResponse,
    BatchRememberRequest,
    BatchRememberResponse,
    BoundedTags,
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
from memanto.app.services.memory_policy_service import (
    MemoryPolicy,
    MemoryPolicyService,
)
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.policy_presets import PRESETS, list_presets, load_preset
from memanto.app.utils.errors import (
    AuthorizationError,
    MemoryOperationError,
    map_error_to_http_exception,
)
from memanto.app.utils.prompt_safety import memory_answer_header_prompt
from memanto.app.utils.temporal_helpers import (
    END_OF_DAY,
    is_date_only,
    parse_date_only,
    utc_date_str,
)
from memanto.app.utils.validation import (
    CostGuard,
    is_successful_write_result,
    validate_safe_id,
)
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.config.manager import ConfigManager

router = APIRouter()

_config_manager = ConfigManager()
_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
logger = logging.getLogger(__name__)


def _sanitize_answer_sources(raw_sources: object) -> list[dict[str, object]]:
    """Return public citations without backend-only document data.

    ``answer.generate`` is a backend boundary and its source shape is not part
    of Memanto's public API.  In particular, returning an object unchanged can
    disclose vector embeddings, namespace names, and provider-specific
    metadata.  Keep only stable citation fields used by callers.
    """
    if not isinstance(raw_sources, list):
        return []

    sanitized: list[dict[str, object]] = []
    for source in raw_sources:
        if isinstance(source, str):
            # Older backend responses can provide only a source identifier.
            # Bound it so an unexpected document body cannot become a large
            # response payload.
            sanitized.append({"id": source[:256]})
            continue
        if not isinstance(source, dict):
            continue

        citation: dict[str, object] = {}
        source_id = source.get("id")
        if isinstance(source_id, str):
            citation["id"] = source_id[:256]
        title = source.get("title")
        if isinstance(title, str):
            citation["title"] = title[:512]
        score = source.get("score")
        if isinstance(score, int | float) and not isinstance(score, bool):
            citation["score"] = score
        source_ref = source.get("source_ref")
        if isinstance(source_ref, str):
            citation["source_ref"] = source_ref[:512]
        if citation:
            sanitized.append(citation)

    return sanitized


def _validate_summary_key(agent_id: str, date_str: str) -> None:
    """Reject identifiers that are unsafe for summary/conflict file paths."""
    if not _SAFE_DATE_RE.fullmatch(date_str):
        raise HTTPException(status_code=400, detail="Invalid summary identifier")
    try:
        validate_safe_id(agent_id, "agent_id")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid summary identifier")


def _validate_memory_type_filters(value: list[str] | None) -> list[str] | None:
    """Validate optional memory type filters against supported memory types."""
    if value is None:
        return value

    invalid = [
        memory_type for memory_type in value if memory_type not in VALID_MEMORY_TYPES
    ]
    if invalid:
        valid_types = ", ".join(sorted(VALID_MEMORY_TYPES))
        raise ValueError(
            f"Invalid memory type filter(s): {', '.join(invalid)}. "
            f"Must be one of: {valid_types}."
        )
    return value


STATUS_FILTER_DESCRIPTION = (
    "Lifecycle filter: 'all' (default) returns active and expired memories "
    "together so callers can label them, 'active' or 'expired' narrows to one."
)


class RecallRequest(BaseModel):
    """Request body for semantic memory recall."""

    query: str = Field(..., min_length=1, description="Search query")
    limit: int | None = Field(default=None, ge=1, description="Max results")
    status: StatusFilter = Field(default="all", description=STATUS_FILTER_DESCRIPTION)
    min_similarity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score (0-1)"
    )
    type: list[str] | None = Field(default=None, description="Memory type filters")
    tags: list[str] | None = Field(default=None, description="Tag filters")
    created_after: datetime | date | None = Field(
        default=None,
        description=(
            "Include only memories created at or after this timestamp. "
            "Date-only values (YYYY-MM-DD) use the start of that day."
        ),
    )
    created_before: datetime | date | None = Field(
        default=None,
        description=(
            "Include only memories created at or before this timestamp. "
            "Date-only values (YYYY-MM-DD) use the end of that day."
        ),
    )

    @field_validator("created_after", mode="before")
    @classmethod
    def parse_created_after(cls, v: object) -> datetime | None:
        """Parse the inclusive lower timestamp bound for recall."""

        if v is None:
            return None
        return _parse_recall_temporal_bound(v, end_of_day=False)

    @field_validator("created_before", mode="before")
    @classmethod
    def parse_created_before(cls, v: object) -> datetime | None:
        """Parse the inclusive upper timestamp bound for recall."""

        if v is None:
            return None
        return _parse_recall_temporal_bound(v, end_of_day=True)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """Reject recall queries that contain only whitespace."""
        if not value.strip():
            raise ValueError("query must be a non-empty string")
        return value

    @field_validator("type")
    @classmethod
    def type_filters_must_be_valid(cls, value: list[str] | None) -> list[str] | None:
        """Reject recall filters that are not supported memory types."""
        return _validate_memory_type_filters(value)


def _parse_recall_temporal_bound(v: object, *, end_of_day: bool) -> datetime:
    # End-of-day must be END_OF_DAY (23:59:59.999999), matching
    # parse_as_of_timestamp: the temporal filter compares with a strict `>`,
    # so a 23:59:59 bound silently drops memories created in the final
    # sub-second of the requested day. Date-only detection is delegated to the
    # shared helper for the same reason as RecallAsOfRequest.parse_as_of.
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        boundary = END_OF_DAY if end_of_day else time(0, 0, 0)
        return datetime.combine(v, boundary, tzinfo=timezone.utc)
    if isinstance(v, str):
        if is_date_only(v):
            try:
                boundary = END_OF_DAY if end_of_day else time(0, 0, 0)
                return datetime.combine(
                    parse_date_only(v), boundary, tzinfo=timezone.utc
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
    raise ValueError(f"Cannot parse temporal recall bound from {type(v)}")


class RecallAsOfRequest(BaseModel):
    """Request body for point-in-time memory recall."""

    as_of: datetime = Field(
        ...,
        description="Point-in-time — YYYY-MM-DD (defaults to end of day) or full ISO datetime e.g. 2025-11-01T14:30:00Z",
    )
    limit: int | None = Field(default=None, ge=1, description="Max results")
    type: list[str] | None = Field(default=None, description="Memory type filters")
    tags: list[str] | None = Field(default=None, description="Tag filters")

    @field_validator("type")
    @classmethod
    def type_filters_must_be_valid(cls, value: list[str] | None) -> list[str] | None:
        """Reject as-of recall filters that are not supported memory types."""
        return _validate_memory_type_filters(value)

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_as_of(cls, v: object) -> datetime:
        """Parse date-only or ISO datetime inputs into an aware timestamp."""
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, date):
            return datetime.combine(v, END_OF_DAY, tzinfo=timezone.utc)
        if isinstance(v, str):
            # Date-only (no time component) → end of day. Delegated to the shared
            # helper so this route and the read service cannot drift apart.
            if is_date_only(v):
                try:
                    return datetime.combine(
                        parse_date_only(v), END_OF_DAY, tzinfo=timezone.utc
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
    tags: list[str] | None = Field(default=None, description="Tag filters")
    status: StatusFilter = Field(default="all", description=STATUS_FILTER_DESCRIPTION)

    @field_validator("type")
    @classmethod
    def type_filters_must_be_valid(cls, value: list[str] | None) -> list[str] | None:
        """Reject changed-since recall filters that are not supported memory types."""
        return _validate_memory_type_filters(value)

    @field_validator("since", mode="before")
    @classmethod
    def parse_since(cls, v: object) -> datetime:
        """Parse date-only or ISO datetime inputs for change filtering."""
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, date):
            return datetime.combine(v, time(0, 0, 0), tzinfo=timezone.utc)
        if isinstance(v, str):
            # Date-only (no time component) → start of day. Uses the same shared
            # helper as the other date-only paths in this module so all three
            # agree on what counts as a date, on every supported Python.
            if is_date_only(v):
                try:
                    return datetime.combine(
                        parse_date_only(v), time(0, 0, 0), tzinfo=timezone.utc
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
    tags: list[str] | None = Field(default=None, description="Tag filters")
    status: StatusFilter = Field(default="all", description=STATUS_FILTER_DESCRIPTION)
    created_after: datetime | date | None = Field(
        default=None,
        description=(
            "Include only memories created at or after this timestamp. "
            "Date-only values (YYYY-MM-DD) use the start of that day."
        ),
    )
    created_before: datetime | date | None = Field(
        default=None,
        description=(
            "Include only memories created at or before this timestamp. "
            "Date-only values (YYYY-MM-DD) use the end of that day."
        ),
    )

    @field_validator("type")
    @classmethod
    def type_filters_must_be_valid(cls, value: list[str] | None) -> list[str] | None:
        """Reject recent-recall filters that are not supported memory types."""
        return _validate_memory_type_filters(value)

    @field_validator("created_after", mode="before")
    @classmethod
    def parse_created_after(cls, v: object) -> datetime | None:
        """Parse the inclusive lower timestamp bound for recent recall."""

        if v is None:
            return None
        return _parse_recall_temporal_bound(v, end_of_day=False)

    @field_validator("created_before", mode="before")
    @classmethod
    def parse_created_before(cls, v: object) -> datetime | None:
        """Parse the inclusive upper timestamp bound for recent recall."""

        if v is None:
            return None
        return _parse_recall_temporal_bound(v, end_of_day=True)


class MemoryExpireRequest(BaseModel):
    """Request body for expiring a single memory."""

    reason: str = Field(
        default="manual",
        description=(
            "Why this memory expired, stamped as `expired_by`. Defaults to "
            "'manual'. Bounded to letters, digits, '.', '_' and '-'."
        ),
    )


class PolicyPresetRequest(BaseModel):
    """Request body for adopting a predefined policy bundle."""

    name: str = Field(..., description="Preset name, e.g. 'balanced'")


class PolicyApplyRequest(BaseModel):
    """Request body for a policy sweep or purge."""

    dry_run: bool = Field(
        default=False,
        description="Report what would change without writing anything",
    )


class MemoryEditRequest(BaseModel):
    """Request body for partial memory record updates."""

    title: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, max_length=10000)
    type: MemoryType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: BoundedTags | None = None
    source: MemorySource | None = None

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


def resolve_recall_limit(request_limit: int | None) -> int:
    """Resolve and validate the effective recall result limit."""

    recall_cfg = _config_manager.get_recall_config()
    raw_limit = (
        request_limit
        if request_limit is not None
        else recall_cfg.get("limit", settings.RECALL_LIMIT)
    )
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid recall configuration: {e}"
        ) from e
    if limit < 1:
        raise HTTPException(
            status_code=400, detail="Invalid recall configuration: limit must be >= 1"
        )
    CostGuard.validate_k_limit(limit)
    return limit


@router.post("/{agent_id}/remember", response_model=RememberResponse)
async def remember(
    agent_id: str,
    request: RememberRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
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
        status = str(result.get("status", "unknown"))
        response_status = "queued" if is_successful_write_result(result) else status

        # Log to local session Markdown summary only after a durable write.
        if is_successful_write_result(result):
            session_service = get_session_service()
            await asyncio.to_thread(
                session_service.try_log_memory_to_session_summary,
                agent_id=agent_id,
                session_id=session.session_id,
                memory_record=memory,
                memory_id=result.get("id"),
            )

        return {
            "memory_id": result["id"],
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": session.namespace,
            "status": response_status,
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
    client=Depends(get_server_moorcheh_client),
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
            CostGuard.validate_text_length(item.content, "Memory content")
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

        batch_results = result.get("results", [])
        for index, record in enumerate(memory_records):
            item_result = batch_results[index] if index < len(batch_results) else None
            if not is_successful_write_result(item_result):
                continue
            memory_id = item_result.get("id") if isinstance(item_result, dict) else None
            await asyncio.to_thread(
                session_service.try_log_memory_to_session_summary,
                agent_id=agent_id,
                session_id=session.session_id,
                memory_record=record,
                memory_id=memory_id,
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
    client=Depends(get_server_moorcheh_client),
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
    client=Depends(get_server_moorcheh_client),
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

        if not isinstance(result, dict):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed batch result from storage layer.",
                details={"item_preview": str(result)[:100]},
            )

        batch_results = result.get("results", [])
        if not isinstance(batch_results, list):
            raise MemoryOperationError(
                message="Data corruption detected: Received malformed batch result array from storage layer.",
                details={"item_preview": str(batch_results)[:100]},
            )

        for index, record in enumerate(memory_records):
            item_result = batch_results[index] if index < len(batch_results) else None
            if item_result is not None and (
                not isinstance(item_result, dict) or not item_result
            ):
                raise MemoryOperationError(
                    message="Data corruption detected: Received malformed batch result from storage layer.",
                    details={"item_preview": str(item_result)[:100]},
                )

            memory_id = item_result.get("id") if item_result else None
            if not is_successful_write_result(item_result):
                continue
            await asyncio.to_thread(
                session_service.try_log_memory_to_session_summary,
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

    client = get_server_moorcheh_client()

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
        # Stream file to disk in 1 MB chunks instead of loading it all into
        # memory at once. Without this, a 5 GB upload would allocate ~5 GB of
        # RAM in a single Python bytes object, making the server trivially
        # exhaustible under concurrent large-file uploads.
        _MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB as documented
        _CHUNK_SIZE = 1024 * 1024  # 1 MB
        try:
            total_bytes = 0
            with open(tmp_path, "wb") as tmp:
                while True:
                    chunk = await file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "error": "file_too_large",
                                "message": "File exceeds the maximum upload size of 5 GB",
                                "max_bytes": _MAX_UPLOAD_BYTES,
                            },
                        )
                    await asyncio.to_thread(tmp.write, chunk)
            result = await asyncio.to_thread(
                client.documents.upload_file, namespace, tmp_path
            )
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

        file_size = result.get("fileSize")
        if file_size is None:
            file_size = result.get("file_size")

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": namespace,
            "file_name": original_name,
            "file_size": file_size,
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
    client=Depends(get_server_moorcheh_client),
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
    client=Depends(get_server_moorcheh_client),
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
    raw_min_similarity = (
        request.min_similarity
        if request.min_similarity is not None
        else recall_cfg.get("min_similarity")
    )
    try:
        limit = resolve_recall_limit(request.limit)
        min_similarity = (
            None if raw_min_similarity is None else float(raw_min_similarity)
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid recall configuration: {e}"
        )
    try:
        # Initialize memory read service
        read_service = MemoryReadService(client)

        # Search in agent's namespace using scope.
        result = await asyncio.to_thread(
            read_service.search_memories,
            query=request.query,
            agent_id=agent_id,
            type=request.type,
            tags=request.tags,
            min_similarity_score=min_similarity,
            created_after=request.created_after.isoformat()
            if request.created_after
            else None,
            created_before=request.created_before.isoformat()
            if request.created_before
            else None,
            status=request.status,
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

    client = get_server_moorcheh_client()

    # Resolve defaults from settings
    limit = request.limit if request.limit is not None else settings.ANSWER_LIMIT
    CostGuard.validate_k_limit(limit)
    temperature = (
        request.temperature
        if request.temperature is not None
        else settings.ANSWER_TEMPERATURE
    )
    resolved_ai_model = (
        request.ai_model
        if request.ai_model is not None
        else get_active_llm_model(settings.ANSWER_MODEL)
    )

    try:
        # Use namespace from session
        namespace = session.namespace

        # Internal fixed prompts (not user-configurable via API contract)
        header_prompt = memory_answer_header_prompt()

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
            "kiosk_mode": request.kiosk_mode,
            "header_prompt": header_prompt,
            "footer_prompt": footer_prompt,
        }
        if resolved_ai_model is not None:
            generate_kwargs["ai_model"] = resolved_ai_model
        if request.kiosk_mode:
            generate_kwargs["threshold"] = (
                request.threshold if request.threshold is not None else 0.15
            )

        response = await asyncio.to_thread(client.answer.generate, **generate_kwargs)

        # Extract the generated answer and sources
        answer = response.get("answer", "No answer generated.")
        sources = _sanitize_answer_sources(response.get("sources", []))

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "question": request.question,
            "answer": answer,
            "sources": sources,
        }

    except Exception as exc:
        # Provider error bodies can contain request data, namespace IDs,
        # embeddings, and service topology. Never relay those details.
        logger.warning("Answer generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "AnswerGenerationFailed",
                "message": "Unable to generate an answer from memory right now.",
            },
        ) from exc


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

    resolved_date = request.date or utc_date_str()
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

    resolved_date = request.date or utc_date_str()
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

    resolved_date = date or utc_date_str()
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

    resolved_date = request.date or utc_date_str()
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
    client=Depends(get_server_moorcheh_client),
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

    limit = resolve_recall_limit(request.limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_as_of,
            as_of_date=request.as_of.isoformat(),
            agent_id=agent_id,
            type=request.type,
            tags=request.tags,
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
    client=Depends(get_server_moorcheh_client),
):
    """
    Differential retrieval: "What changed recently?"

    Returns memories created or updated after the specified datetime.

    Example: "What changed since last week?"

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    limit = resolve_recall_limit(request.limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_changed_since,
            since_date=request.since.isoformat(),
            agent_id=agent_id,
            type=request.type,
            tags=request.tags,
            status=request.status,
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
    client=Depends(get_server_moorcheh_client),
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

    limit = resolve_recall_limit(request.limit)

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_recent,
            agent_id=agent_id,
            type=request.type,
            tags=request.tags,
            status=request.status,
            limit=limit,
            created_after=request.created_after.isoformat()
            if request.created_after
            else None,
            created_before=request.created_before.isoformat()
            if request.created_before
            else None,
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


# Memory lifecycle: expire / restore


@router.post("/{agent_id}/memories/{memory_id}/expire")
async def expire_memory(
    agent_id: str,
    memory_id: str,
    request: MemoryExpireRequest = Body(default=MemoryExpireRequest()),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Expire one memory without deleting it (Session-based).

    The memory stays recallable and keeps its content; it is stamped
    ``expired`` with the time and reason, and labelled as such in recall.
    Reversible via the restore endpoint.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        write_service = MemoryWriteService(client)
        result = await asyncio.to_thread(
            write_service.set_lifecycle,
            memory_id,
            session.namespace,
            expired=True,
            reason=request.reason,
        )
        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "memory_id": memory_id,
            "status": "expired",
            "expired_at": result.get("expired_at"),
            "expired_by": result.get("expired_by"),
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404, detail=f"Memory '{memory_id}' was not found."
            )
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/memories/{memory_id}/restore")
async def restore_memory(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Return an expired memory to the active state (Session-based).

    Clears the expiry stamp entirely.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        write_service = MemoryWriteService(client)
        await asyncio.to_thread(
            write_service.set_lifecycle,
            memory_id,
            session.namespace,
            expired=False,
        )
        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "memory_id": memory_id,
            "status": "active",
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404, detail=f"Memory '{memory_id}' was not found."
            )
        raise map_error_to_http_exception(e)


# Expiry policies


@router.get("/{agent_id}/policy")
async def get_policy(
    agent_id: str,
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Return the agent's expiry policy (Session-based).

    An agent with no policy set returns an empty one, which expires nothing.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        service = MemoryPolicyService(client)
        policy = await asyncio.to_thread(service.load_policy, agent_id)
        return {
            "agent_id": agent_id,
            "policy": policy.model_dump(mode="json", exclude_none=True),
            "is_empty": policy.is_empty(),
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.put("/{agent_id}/policy")
async def set_policy(
    agent_id: str,
    policy: MemoryPolicy = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Replace the agent's expiry policy (Session-based).

    Saving a policy does not expire anything on its own — run the apply
    endpoint, or let the nightly sweep pick it up.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        service = MemoryPolicyService(client)
        path = await asyncio.to_thread(service.save_policy, agent_id, policy)
        return {
            "agent_id": agent_id,
            "policy": policy.model_dump(mode="json", exclude_none=True),
            "path": str(path),
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/policy/presets")
async def list_policy_presets(
    agent_id: str,
    session: Session = Depends(get_current_session),
):
    """
    List the predefined policy bundles (Session-based).

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)
    return {"presets": list_presets()}


@router.get("/{agent_id}/policy/presets/{name}")
async def get_policy_preset(
    agent_id: str,
    name: str,
    session: Session = Depends(get_current_session),
):
    """
    Return one preset's full policy without adopting it (Session-based).

    Lets a caller preview exactly what a preset contains before committing,
    which is what makes an informed confirmation possible.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        policy = load_preset(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "name": name,
        "description": PRESETS[name]["description"],
        "policy": policy.model_dump(mode="json", exclude_none=True),
    }


@router.post("/{agent_id}/policy/preset")
async def apply_policy_preset(
    agent_id: str,
    request: PolicyPresetRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Adopt a predefined policy bundle as the agent's policy (Session-based).

    Overwrites any existing policy. Nothing expires until a sweep runs.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        policy = load_preset(request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        service = MemoryPolicyService(client)
        await asyncio.to_thread(service.save_policy, agent_id, policy)
        return {
            "agent_id": agent_id,
            "preset": request.name,
            "policy": policy.model_dump(mode="json", exclude_none=True),
        }
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/policy/apply")
async def apply_policy(
    agent_id: str,
    request: PolicyApplyRequest = Body(default=PolicyApplyRequest()),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Sweep the agent's memories and expire everything the policy matches.

    Pass ``dry_run: true`` to see exactly what would be expired, with per-rule
    counts, without writing anything.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        service = MemoryPolicyService(client)
        return await asyncio.to_thread(
            service.apply_policies, agent_id, dry_run=request.dry_run
        )
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/policy/purge")
async def purge_expired_memories(
    agent_id: str,
    request: PolicyApplyRequest = Body(default=PolicyApplyRequest()),
    session: Session = Depends(get_current_session),
    client=Depends(get_server_moorcheh_client),
):
    """
    Permanently delete memories expired longer than the policy's purge window.

    Destructive and irreversible. Disabled unless the policy sets
    ``purge_expired_after``. Pass ``dry_run: true`` to preview.

    Requires:
    - X-Session-Token: {session_token}
    """
    enforce_session_scope(session, agent_id)

    try:
        service = MemoryPolicyService(client)
        return await asyncio.to_thread(
            service.purge_expired, agent_id, dry_run=request.dry_run
        )
    except Exception as e:
        raise map_error_to_http_exception(e)

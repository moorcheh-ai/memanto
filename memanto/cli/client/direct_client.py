"""
MEMANTO Direct Client

Calls the Moorcheh API directly through existing service classes
"""

import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from memanto.app.constants import (
    ALLOWED_UPDATE_FIELDS as _ALLOWED_UPDATE_FIELDS,
)
from memanto.app.constants import (
    VALID_MEMORY_TYPES as _VALID_MEMORY_TYPES,
)
from memanto.app.constants import (
    VALID_PATTERNS as _VALID_PATTERNS,
)
from memanto.app.constants import (
    VALID_PROVENANCE_TYPES as _VALID_PROVENANCE,
)
from memanto.app.constants import (
    MemoryType,
)
from memanto.app.constants import (
    ProvenanceType as MemoryProvenance,
)
from memanto.app.utils.errors import (
    AgentNotFoundError,
    InvalidSessionTokenError,
    SessionError,
    SessionExpiredError,
    SessionNotFoundError,
)
from memanto.app.utils.validation import InputLimits
from memanto.cli.config.manager import ConfigManager

logger = logging.getLogger(__name__)


# Moorcheh's API Gateway strictly requires lowercase for 'x-api-key'.
# This string subclass defeats urllib's automatic title-casing.
class LowerStr(str):
    def title(self):
        return self

    def capitalize(self):
        return self


class MoorchehClient:
    """
    A lightweight, zero-dependency Moorcheh client using urllib
    """

    def __init__(self, api_key: str, base_url: str = "https://api.moorcheh.ai/v1"):
        self.api_key = api_key
        self.base_url = os.environ.get("MOORCHEH_BASE_URL", base_url).rstrip("/")

    def _request(self, method: str, endpoint: str, json_data: Any = None) -> Any:
        url = f"{self.base_url}{endpoint}"

        headers = {
            LowerStr("x-api-key"): self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "Moorcheh-Client/1.0",
        }

        req_data = (
            json.dumps(json_data).encode("utf-8") if json_data is not None else None
        )
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 204:
                    return {}
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            # Try to return JSON if available
            try:
                err_json = json.loads(body)
                raise Exception(
                    f"Moorcheh API Error {e.code}: {err_json.get('message', body)}"
                )
            except json.JSONDecodeError:
                raise Exception(f"Moorcheh API Error {e.code}: {body}")
        except Exception as e:
            raise Exception(f"Moorcheh Connection Error: {e}")

    @property
    def documents(self):
        class Docs:
            def __init__(self, client):
                self.client = client

            def upload(self, namespace_name, documents):
                return self.client._request(
                    "POST",
                    f"/namespaces/{namespace_name}/documents",
                    {"documents": documents},
                )

            def delete(self, namespace_name, ids):
                return self.client._request(
                    "POST",
                    f"/namespaces/{namespace_name}/documents/delete",
                    {"ids": ids},
                )

            def get(self, namespace_name, ids):
                return self.client._request(
                    "POST", f"/namespaces/{namespace_name}/documents/get", {"ids": ids}
                )

        return Docs(self)

    @property
    def namespaces(self):
        class NS:
            def __init__(self, client):
                self.client = client

            def create(self, namespace_name, type="text"):
                return self.client._request(
                    "POST",
                    "/namespaces",
                    {"namespace_name": namespace_name, "type": type},
                )

            def list(self):
                return self.client._request("GET", "/namespaces")

        return NS(self)

    @property
    def similarity_search(self):
        class Search:
            def __init__(self, client):
                self.client = client

            def query(
                self, namespaces, query, top_k=10, threshold=0.25, kiosk_mode=False
            ):
                payload = {
                    "namespaces": namespaces,
                    "query": query,
                    "top_k": top_k,
                    "kiosk_mode": kiosk_mode,
                }
                if kiosk_mode:
                    payload["threshold"] = threshold
                return self.client._request("POST", "/search", payload)

        return Search(self)

    @property
    def answer(self):
        class Ans:
            def __init__(self, client):
                self.client = client

            def generate(
                self,
                namespace,
                query,
                top_k=None,
                ai_model=None,
                temperature=None,
                threshold=None,
                kiosk_mode=False,
                header_prompt=None,
                footer_prompt=None,
            ):
                ans_cfg = ConfigManager().get_answer_config()
                payload = {
                    "namespace": namespace,
                    "query": query,
                    "top_k": top_k if top_k is not None else ans_cfg["answer_limit"],
                    "type": "text",
                    "aiModel": ai_model if ai_model is not None else ans_cfg["model"],
                    "temperature": temperature
                    if temperature is not None
                    else ans_cfg["temperature"],
                    "kiosk_mode": kiosk_mode,
                    "headerPrompt": header_prompt or "",
                    "footerPrompt": footer_prompt or "",
                }
                if kiosk_mode:
                    payload["threshold"] = (
                        threshold if threshold is not None else ans_cfg["threshold"]
                    )
                return self.client._request("POST", "/answer", payload)

        return Ans(self)

    def close(self):
        pass


logger = logging.getLogger(__name__)

__all__ = ["DirectClient"]


# Constants

_MAX_BATCH_SIZE = 100
_MAX_TITLE_LENGTH = 100
_MAX_CONTENT_LENGTH = InputLimits.MAX_TEXT_LENGTH


class DirectClient:
    """
    Direct SDK client for CLI commands.

    All heavy dependencies (``moorcheh_sdk``, ``app.services.*``,
    ``pydantic`` models) are imported lazily on first use so that
    ``import direct_client`` itself is near-instant.

    Raises:
        ValueError: For invalid input (bad agent_id, pattern, etc.).
        app.utils.errors.AgentNotFoundError: When a referenced agent
            does not exist.
        app.utils.errors.AgentAlreadyExistsError: When creating a
            duplicate agent.
        app.utils.errors.SessionError: For session-related failures.
        ConnectionError: If ``health_check()`` is called (not applicable
            in direct mode).
    """

    def __init__(self, api_key: str) -> None:
        """
        Initialize direct client.

        Args:
            api_key: Moorcheh API key (required, non-empty).

        Raises:
            ValueError: If *api_key* is empty or None.
        """
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")

        self.api_key: str = api_key
        self.session_token: str | None = None
        self.agent_id: str | None = None
        self._cached_session: Any | None = None

        # Lazy-initialized on first use
        self._moorcheh = None
        self._write_service = None
        self._read_service = None
        self._agent_service = None
        self._session_service = None
        self._daily_analysis_service = None
        self._export_service = None

    # Lazy initializers

    def _get_moorcheh(self):
        """Return (or create) the backend-aware Moorcheh client.

        Dispatches to cloud ``MoorchehClient`` or on-prem ``OnPremClient`` based
        on the active backend, mirroring ``SdkClient._get_moorcheh``. Without
        this, on-prem callers (e.g. UI ``batch_remember`` for migrate) hit
        cloud and get a "namespace not found" 404 for agents that only exist
        locally.
        """
        if self._moorcheh is None:
            from memanto.app.clients.moorcheh import get_moorcheh_client

            logger.debug("Initializing Moorcheh client via backend dispatcher")
            self._moorcheh = get_moorcheh_client()
        return self._moorcheh

    def _get_write_service(self):
        """Return (or create) the ``MemoryWriteService`` singleton."""
        if self._write_service is None:
            from memanto.app.services.memory_write_service import MemoryWriteService

            self._write_service = MemoryWriteService(self._get_moorcheh())
        return self._write_service

    def _get_read_service(self):
        """Return (or create) the ``MemoryReadService`` singleton."""
        if self._read_service is None:
            from memanto.app.services.memory_read_service import MemoryReadService

            self._read_service = MemoryReadService(self._get_moorcheh())
        return self._read_service

    def _get_agent_service(self):
        """Return (or create) the ``AgentService`` singleton."""
        if self._agent_service is None:
            from memanto.app.services.agent_service import AgentService

            self._agent_service = AgentService()
        return self._agent_service

    def _get_session_service(self):
        """Return the shared ``SessionService`` singleton."""
        if self._session_service is None:
            from memanto.app.services.session_service import get_session_service

            self._session_service = get_session_service()
        return self._session_service

    def _get_daily_analysis_service(self):
        """Return (or create) the ``DailyAnalysisService`` singleton."""
        if self._daily_analysis_service is None:
            from memanto.app.services.daily_analysis_service import (
                DailyAnalysisService,
            )

            self._daily_analysis_service = DailyAnalysisService()
        return self._daily_analysis_service

    def _get_export_service(self):
        """Return (or create) the ``MemoryExportService`` singleton."""
        if self._export_service is None:
            from memanto.app.services.memory_export_service import MemoryExportService

            self._export_service = MemoryExportService()
        return self._export_service

    # Internal helpers

    def _get_validated_session_for_agent(self, agent_id: str):
        """
        Return the active session for *agent_id*, validating it like the FastAPI
        dependency ``get_current_session``.
        """
        # Cache hit: avoid redundant disk I/O and JWT decodes in the same request
        if self._cached_session and self.agent_id == agent_id:
            return self._cached_session

        if not self.session_token or not self.agent_id:
            raise SessionError(
                "No active session. Call activate_agent() before performing "
                "session-based memory operations."
            )

        # Enforce session scope: stored session must match requested agent_id
        if self.agent_id != agent_id:
            raise SessionError(
                f"Active session is for agent '{self.agent_id}', "
                f"cannot access '{agent_id}'"
            )

        session_service = self._get_session_service()

        try:
            # Validate JWT token
            token_payload = session_service.validate_session(self.session_token)
        except (SessionExpiredError, InvalidSessionTokenError):
            # Surface the same specific session errors as the service
            raise

        # Load the persisted session record
        session = session_service.get_session(token_payload.agent_id)
        if not session:
            raise SessionNotFoundError(
                f"Session for agent {token_payload.agent_id} not found"
            )

        # Check and auto-renew if near expiry. SessionService.renew_session
        # writes the new token to ~/.memanto/sessions/{agent}.json and
        # refreshes the active marker, so no extra persistence is needed here.
        renewed = session_service.check_and_auto_renew(
            agent_id=token_payload.agent_id,
        )
        if renewed:
            session = renewed
            self.session_token = session.session_token

        self._cached_session = session
        return session

    # Agent Management

    def create_agent(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new agent.

        Args:
            agent_id: Unique identifier (alphanumeric, hyphens, underscores).
            pattern: Agent pattern — ``"support"``, ``"project"``, or
                ``"tool"`` (default).
            description: Optional human-readable description.

        Returns:
            Agent info dict with keys ``agent_id``, ``namespace``,
            ``pattern``, ``created_at``, etc.

        Raises:
            ValueError: If *pattern* is invalid.
            AgentAlreadyExistsError: If agent already exists.
        """
        if pattern not in _VALID_PATTERNS:
            raise ValueError(
                f"Invalid pattern '{pattern}'. Must be one of: {', '.join(sorted(_VALID_PATTERNS))}"
            )

        from memanto.app.models.session import AgentCreate, AgentPattern

        agent_create = AgentCreate(
            agent_id=agent_id,
            pattern=AgentPattern(pattern),
            description=description,
        )

        logger.debug("Creating agent '%s' with pattern '%s'", agent_id, pattern)
        agent_info = self._get_agent_service().create_agent(agent_create, self.api_key)
        return cast(dict[str, Any], agent_info.model_dump(mode="json"))

    def list_agents(self) -> list[dict[str, Any]]:
        """
        List all registered agents.

        Returns:
            List of agent info dicts.
        """
        agent_list = self._get_agent_service().list_agents()
        return [a.model_dump(mode="json") for a in agent_list.agents]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """
        Get agent details.

        Args:
            agent_id: Agent identifier.

        Returns:
            Agent info dict.

        Raises:
            AgentNotFoundError: If agent does not exist.
        """
        agent = self._get_agent_service().get_agent(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        return cast(dict[str, Any], agent.model_dump(mode="json"))

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """
        Delete an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Confirmation dict with ``status`` and ``agent_id``.
        """
        logger.debug("Deleting agent '%s'", agent_id)
        self._get_agent_service().delete_agent(agent_id)
        return {"status": "deleted", "agent_id": agent_id}

    # Session Management

    def activate_agent(
        self, agent_id: str, duration_hours: int | None = None
    ) -> dict[str, Any]:
        """
        Activate an agent session.

        Creates a JWT-based session via ``SessionService`` (same logic
        the server uses) and stores the token locally.

        Args:
            agent_id: Agent to activate.
            duration_hours: Session lifetime in hours (default: from config).

        Returns:
            Dict with ``session_token``, ``session_id``, ``agent_id``,
            ``namespace``, ``expires_at``.

        Raises:
            AgentNotFoundError: If agent does not exist.
        """
        agent = self._get_agent_service().get_agent(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        logger.debug("Activating agent '%s' for %d hours", agent_id, duration_hours)
        session = self._get_session_service().create_session(
            agent_id=agent_id,
            pattern=agent.pattern,
            duration_hours=duration_hours,
        )

        self._get_agent_service().update_agent_stats(
            agent_id,
            last_session=session.started_at,
            increment_session_count=True,
        )

        self.session_token = session.session_token
        self.agent_id = agent_id

        return {
            "session_token": session.session_token,
            "session_id": session.session_id,
            "agent_id": agent_id,
            "namespace": session.namespace,
            "expires_at": session.expires_at.isoformat(),
        }

    def deactivate_agent(self, agent_id: str) -> dict[str, Any]:
        """
        Deactivate agent session.

        Args:
            agent_id: Agent whose session to end.

        Returns:
            Session summary dict.
        """
        logger.debug("Deactivating agent '%s'", agent_id)
        summary = self._get_session_service().end_session(agent_id)
        self.session_token = None
        self.agent_id = None
        return cast(dict[str, Any], summary.model_dump(mode="json"))

    def get_session_info(self) -> dict[str, Any]:
        """
        Get current session info.

        Returns:
            Dict with session details including ``time_remaining_seconds``.

        Raises:
            ValueError: If no active agent/session.
            SessionNotFoundError: If session data is missing.
            SessionExpiredError / InvalidSessionTokenError: If session token is invalid.
        """
        if not self.agent_id:
            raise ValueError("No active agent")

        # Validate session for this agent
        session = self._get_validated_session_for_agent(self.agent_id)

        remaining = session.time_remaining()
        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "namespace": session.namespace,
            "pattern": session.pattern.value if session.pattern else "unknown",
            "status": session.status.value,
            "started_at": session.started_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "time_remaining_seconds": max(0, int(remaining.total_seconds())),
        }

    # Memory Operations

    def remember(
        self,
        agent_id: str,
        memory_type: str | None,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "user",
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """
        Store a single memory.

        Args:
            agent_id: Target agent.
            memory_type: One of ``fact``, ``preference``, ``goal``,
                ``decision``, ``artifact``, ``learning``, ``event``,
                ``instruction``, ``relationship``, ``context``,
                ``observation``, ``commitment``, ``error``.
            title: Memory title (max 100 chars).
            content: Memory content (max ``InputLimits.MAX_TEXT_LENGTH`` chars).
            confidence: Confidence score 0.0–1.0 (default 0.8).
            tags: Optional list of tags.
            source: Memory source (default ``"user"``).

        Returns:
            Dict with ``memory_id``, ``agent_id``, ``namespace``,
            ``status``, ``confidence``.

        Raises:
            ValueError: If *memory_type* is invalid or *confidence* is
                out of range.
        """
        # Ensure there is a valid, non-expired session for this agent
        session = self._get_validated_session_for_agent(agent_id)
        _ = session

        self._validate_memory_input(memory_type, title, content, confidence)

        resolved_memory_type = (
            cast(MemoryType, memory_type) if memory_type is not None else None
        )
        resolved_provenance = provenance or "explicit_statement"
        if resolved_provenance not in _VALID_PROVENANCE:
            raise ValueError(
                f"Invalid provenance '{resolved_provenance}'. "
                f"Must be one of: {', '.join(sorted(_VALID_PROVENANCE))}"
            )
        resolved_provenance = cast(MemoryProvenance, resolved_provenance)

        from memanto.app.core import MemoryRecord

        memory = MemoryRecord(
            type=resolved_memory_type,
            title=title,
            content=content,
            agent_id=agent_id,
            actor_id=agent_id,
            confidence=confidence,
            tags=tags or [],
            source=source,
            provenance=resolved_provenance,
        )

        logger.debug("Storing memory for agent '%s' (type=%s)", agent_id, memory_type)
        result = self._get_write_service().store_memory(memory)

        # Log to local session Markdown summary
        if self.session_token:
            session_id = "unknown"
            self._get_session_service().log_memory_to_session_summary(
                agent_id=agent_id,
                session_id=session_id,
                memory_record=memory,
                memory_id=result.get("id"),
            )

        return {
            "memory_id": result["id"],
            "agent_id": agent_id,
            "namespace": result.get("namespace"),
            "status": result.get("status", "queued"),
            "confidence": confidence,
            "type": result.get("type"),
        }

    def batch_remember(
        self, agent_id: str, memories: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Store multiple memories in batch.

        Args:
            agent_id: Target agent.
            memories: List of memory dicts (max 100). Each dict must
                have ``content`` and may have ``type``, ``title``,
                ``confidence``, ``tags``.

        Returns:
            Batch result dict with ``total_submitted``, ``successful``,
            ``failed``, ``results``.

        Raises:
            ValueError: If batch is empty or exceeds 100 items.
        """
        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        if not memories:
            raise ValueError("Batch must contain at least one memory")
        if len(memories) > _MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size {len(memories)} exceeds maximum of {_MAX_BATCH_SIZE}"
            )

        from memanto.app.core import MemoryRecord

        memory_records = []
        for i, item in enumerate(memories):
            raw_content = item.get("content", "")
            if not raw_content:
                raise ValueError(f"Memory at index {i} has no content")

            raw_title = item.get("title")
            title = raw_title or (
                raw_content[:47] + "..." if len(raw_content) > 50 else raw_content
            )
            raw_type = item.get("type")

            # Optional per-item overrides for the migrate flow — keep source
            # provenance, original ids, and source-side timestamps. Defaults
            # preserve the original single-user-write behavior.
            provenance = item.get("provenance") or "explicit_statement"
            if provenance not in _VALID_PROVENANCE:
                raise ValueError(
                    f"Invalid provenance '{provenance}' at index {i}. "
                    f"Must be one of: {', '.join(sorted(_VALID_PROVENANCE))}"
                )

            kwargs: dict[str, Any] = {
                "type": raw_type,
                "title": title,
                "content": raw_content,
                "agent_id": agent_id,
                "actor_id": agent_id,
                "confidence": item.get("confidence", 0.8),
                "tags": item.get("tags", []),
                "source": item.get("source") or "user",
                "provenance": provenance,
            }
            for opt_key in ("source_ref", "created_at", "updated_at"):
                val = item.get(opt_key)
                if val is not None:
                    kwargs[opt_key] = val

            memory = MemoryRecord(**kwargs)
            memory_records.append(memory)

        logger.debug(
            "Batch storing %d memories for agent '%s'",
            len(memory_records),
            agent_id,
        )
        result = cast(
            dict[str, Any],
            self._get_write_service().batch_store_memories(memory_records),
        )

        # Log each memory to local session Markdown summary
        if self.session_token:
            session_id = "unknown"
            session_svc = self._get_session_service()

            # Extract per-memory IDs from the batch result
            batch_results = result.get("results", [])

            for i, mem in enumerate(memory_records):
                mem_id = batch_results[i].get("id") if i < len(batch_results) else None
                session_svc.log_memory_to_session_summary(
                    agent_id=agent_id,
                    session_id=session_id,
                    memory_record=mem,
                    memory_id=mem_id,
                )

        return result

    def update_memory(
        self, agent_id: str, memory_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update a single memory in the active agent namespace.

        Args:
            agent_id: Target agent.
            memory_id: Memory document ID to update.
            updates: Fields to update.

        Returns:
            Dict with update result metadata.

        Raises:
            ValueError: If no update fields are provided.
        """
        session = self._get_validated_session_for_agent(agent_id)
        if not updates:
            raise ValueError("Provide at least one field to update")
        unknown_fields = set(updates) - _ALLOWED_UPDATE_FIELDS
        if unknown_fields:
            raise ValueError(
                f"Unknown update fields: {', '.join(sorted(unknown_fields))}. "
                f"Allowed fields: {', '.join(sorted(_ALLOWED_UPDATE_FIELDS))}."
            )
        if "content" in updates:
            content = updates["content"]
            if content is None or not str(content).strip():
                raise ValueError("Memory content must be a non-empty string")
            if len(str(content)) > _MAX_CONTENT_LENGTH:
                raise ValueError(
                    f"Memory content exceeds {_MAX_CONTENT_LENGTH} characters"
                )
        if "title" in updates:
            title = updates["title"]
            if title is not None and len(str(title)) > _MAX_TITLE_LENGTH:
                raise ValueError(f"Memory title exceeds {_MAX_TITLE_LENGTH} characters")
        if "type" in updates:
            memory_type = updates["type"]
            if memory_type not in _VALID_MEMORY_TYPES:
                raise ValueError(
                    f"Invalid memory_type '{memory_type}'. "
                    f"Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}"
                )
        if "confidence" in updates:
            try:
                confidence_value = float(updates["confidence"])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                raise ValueError(
                    f"Confidence must be a number between 0.0 and 1.0, got {updates['confidence']!r}"
                )
            if not 0.0 <= confidence_value <= 1.0:
                raise ValueError(
                    f"Confidence must be between 0.0 and 1.0, got {confidence_value}"
                )
            # Normalize to float so downstream write service persists a numeric
            # confidence even when the caller passed "0.7" as a string. CodeRabbit
            # review 2026-06-14T14:03:20Z flagged that string values were
            # previously forwarded unchanged.
            updates["confidence"] = confidence_value

        result = self._get_write_service().update_memory(
            memory_id, session.namespace, updates
        )

        return {
            "agent_id": agent_id,
            "namespace": session.namespace,
            "memory_id": memory_id,
            "status": result.get("status", "updated"),
            "action": result.get("action", "updated"),
            "updated_fields": result.get("updated_fields", list(updates.keys())),
        }

    def extract_memories_from_conversation(
        self,
        agent_id: str,
        messages: list[dict[str, str]],
        dry_run: bool = False,
        max_memories: int = 20,
        ai_model: str | None = None,
    ) -> dict[str, Any]:
        """
        Extract typed memories from conversation turns.

        Args:
            agent_id: Target agent.
            messages: Chat-style messages with ``role`` and ``content`` keys.
            dry_run: When True, preview extracted candidates without storing them.
            max_memories: Maximum number of candidate memories to extract.
            ai_model: Optional model override for extraction.

        Returns:
            A dictionary containing extracted candidates and, unless ``dry_run``
            is enabled, the batch storage result.

        Raises:
            SessionError: If no active session exists for the agent.
        """

        session = self._get_validated_session_for_agent(agent_id)

        from memanto.app.services.conversation_memory_extraction_service import (
            ConversationMemoryExtractionService,
        )

        service = ConversationMemoryExtractionService(self._get_moorcheh())
        candidates = service.extract(
            namespace=session.namespace,
            messages=messages,
            max_memories=max_memories,
            ai_model=ai_model,
        )

        if dry_run:
            return {
                "dry_run": True,
                "candidates": candidates,
                "count": len(candidates),
            }

        result = self.batch_remember(agent_id=agent_id, memories=candidates)
        return {
            "dry_run": False,
            "candidates": candidates,
            **result,
        }

    def delete_memory(self, agent_id: str, memory_id: str) -> dict[str, Any]:
        """
        Delete one memory from the active agent namespace.

        Args:
            agent_id: Target agent.
            memory_id: Memory document ID to delete.

        Returns:
            Confirmation dict with ``status``, ``agent_id``, ``memory_id``, and
            ``namespace``.

        Raises:
            ValueError: If the memory does not exist in the active agent namespace.
        """
        session = self._get_validated_session_for_agent(agent_id)
        namespace = session.namespace

        logger.debug(
            "Deleting memory '%s' from agent '%s' namespace '%s'",
            memory_id,
            agent_id,
            namespace,
        )
        deleted = self._get_write_service().delete_memory(memory_id, namespace)
        if not deleted:
            raise ValueError(
                f"Memory '{memory_id}' was not found for agent '{agent_id}'"
            )

        # Log deletion to local session Markdown summary
        if self.session_token:
            self._get_session_service().log_memory_deletion_to_session_summary(
                agent_id=agent_id,
                session_id=session.session_id,
                memory_id=memory_id,
            )

        return {
            "status": "deleted",
            "agent_id": agent_id,
            "memory_id": memory_id,
            "namespace": namespace,
        }

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_similarity: float | None = None,
        min_confidence: float | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Search memories by semantic similarity.

        Args:
            agent_id: Target agent.
            query: Natural-language search query.
            limit: Max results (1–100, defaults to config).
            type: Filter by types (e.g. ``["fact", "decision"]``).
            tags: Filter by tags.
            min_similarity: Minimum similarity threshold.
            min_confidence: Minimum confidence threshold.
            created_after: Only memories created after this datetime.
            created_before: Only memories created before this datetime.

        Returns:
            Dict with ``agent_id``, ``query``, ``memories`` (list),
            ``count``.
        """
        recall_cfg = ConfigManager().get_recall_config()
        if limit is None:
            limit = recall_cfg["limit"]
        if min_similarity is None:
            min_similarity = recall_cfg.get("min_similarity")

        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        self._validate_query(query, limit)

        logger.debug(
            "Recall for agent '%s': query='%s', limit=%d", agent_id, query, limit
        )
        result = self._get_read_service().search_memories(
            query=query,
            agent_id=agent_id,
            type=type,
            tags=tags,
            min_confidence=min_confidence,
            min_similarity_score=min_similarity,
            created_after=created_after.isoformat() if created_after else None,
            created_before=created_before.isoformat() if created_before else None,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "query": query,
            "memories": result.get("results", []),
            "count": result.get("total_found", 0),
        }

    def recall_as_of(
        self,
        agent_id: str,
        as_of: str,
        limit: int | None = None,
        type: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Point-in-time recall: what memories existed at a given moment?

        Args:
            agent_id: Target agent.
            as_of: ISO-8601 date/datetime string.
            limit: Max results (defaults to config).
            type: Optional type filter.

        Returns:
            Dict with ``memories`` and ``count``.
        """
        if limit is None:
            limit = ConfigManager().get_recall_config()["limit"]

        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        result = self._get_read_service().search_as_of(
            as_of_date=as_of,
            agent_id=agent_id,
            type=type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "as_of_date": as_of,
            "memories": result.get("results", []),
            "count": result.get("total_found", 0),
        }

    def recall_changed_since(
        self,
        agent_id: str,
        since: str,
        limit: int | None = None,
        type: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Differential retrieval: what changed since a given date?

        Args:
            agent_id: Target agent.
            since: ISO-8601 date/datetime string.
            limit: Max results (defaults to config).
            type: Optional type filter.

        Returns:
            Dict with ``memories`` and ``count``.
        """
        if limit is None:
            limit = ConfigManager().get_recall_config()["limit"]

        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        result = self._get_read_service().search_changed_since(
            since_date=since,
            agent_id=agent_id,
            type=type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "since_date": since,
            "memories": result.get("results", []),
            "count": result.get("total_found", 0),
        }

    def recall_recent(
        self,
        agent_id: str,
        limit: int | None = None,
        type: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Recall the most recently stored memories (newest first).

        Args:
            agent_id: Target agent.
            limit: Max results (defaults to config).
            type: Optional type filter.

        Returns:
            Dict with ``memories`` and ``count``.
        """
        if limit is None:
            limit = ConfigManager().get_recall_config()["limit"]

        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        result = self._get_read_service().search_recent(
            agent_id=agent_id,
            type=type,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "memories": result.get("results", []),
            "count": result.get("total_found", 0),
        }

    def answer(
        self,
        agent_id: str,
        question: str,
        limit: int | None = None,
        threshold: float | None = None,
        temperature: float | None = None,
        ai_model: str | None = None,
        kiosk_mode: bool | None = None,
        header_prompt: str | None = None,
        footer_prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Answer a question using RAG (Retrieval-Augmented Generation).

        Retrieves the most relevant memories and passes them as context
        to the Moorcheh LLM to generate a grounded answer.

        Args:
            agent_id: Target agent.
            question: Natural-language question.
            limit: Number of memories to use as context (defaults to config).
            threshold: Similarity threshold. Only honored when
                ``kiosk_mode`` is True. Defaults to the config value when
                unset.
            temperature: Temperature for the LLM response (defaults to config).
            ai_model: AI model to use for generating the answer (defaults to config).
            kiosk_mode: When True, filters out low-relevance results using
                ``threshold``. When None (default), reads the config value.
            header_prompt: Header prompt for the LLM.
            footer_prompt: Footer prompt for the LLM.

        Returns:
            Dict with ``answer``, ``sources``, ``namespace``.
        """
        # Resolve defaults from config
        ans_cfg = ConfigManager().get_answer_config()
        if limit is None:
            limit = ans_cfg["answer_limit"]
        if temperature is None:
            temperature = ans_cfg["temperature"]
        if ai_model is None:
            ai_model = ans_cfg["model"]
        if kiosk_mode is None:
            kiosk_mode = bool(ans_cfg.get("kiosk_mode", False))
        # Threshold is only meaningful in kiosk_mode; only fall back to the
        # config value when the caller has actually turned kiosk_mode on.
        if kiosk_mode and threshold is None:
            threshold = ans_cfg["threshold"]

        # Ensure there is a valid, non-expired session for this agent
        session = self._get_validated_session_for_agent(agent_id)

        if not question or not question.strip():
            raise ValueError("Question must be a non-empty string")

        # get namespace from session
        namespace = session.namespace

        header_prompt = header_prompt or (
            "You are a helpful AI assistant with access to the agent's persistent memory. "
            "Use the provided context from the agent's memories to answer the user's question accurately. "
            "If the memories don't contain relevant information, say so clearly."
        )

        footer_prompt = footer_prompt or (
            "Answer the question based on the memory context above. "
            "Be concise and cite specific memories when relevant. "
            "If no relevant memories exist, acknowledge that."
        )

        logger.debug(
            "RAG answer for agent '%s': question='%s', top_k=%d",
            agent_id,
            question[:80],
            limit,
        )
        response = self._get_moorcheh().answer.generate(
            namespace=namespace,
            query=question,
            top_k=limit,
            threshold=threshold,
            temperature=temperature,
            ai_model=ai_model,
            kiosk_mode=kiosk_mode,
            header_prompt=header_prompt,
            footer_prompt=footer_prompt,
        )

        return {
            "agent_id": agent_id,
            "question": question,
            "answer": response.get("answer", "No answer generated."),
            "sources": response.get("sources", []),
            "namespace": namespace,
        }

    def generate_daily_summary(
        self, agent_id: str, date: str, output_path: str | None = None
    ) -> dict[str, Any]:
        """
        Generate a daily AI summary from session MD files (on-demand).

        Conflict detection is a separate concern — see
        :meth:`generate_conflict_report`.

        Args:
            agent_id: Target agent.
            date: Date string (YYYY-MM-DD).
            output_path: Optional custom output path for the summary MD file.

        Returns:
            Dict with ``summary`` and ``export`` sub-results.
        """
        # Ensure agent exists
        self.get_agent(agent_id)

        logger.debug(
            "Generating daily summary for agent '%s' on %s",
            agent_id,
            date,
        )

        service = self._get_daily_analysis_service()

        summary_result = service.generate_summary(
            agent_id, date, output_path=output_path
        )

        # Auto-export memories to keep local MD cache up to date
        try:
            export_result = self.export_memory_md(agent_id)
        except Exception as e:
            logger.warning(
                f"Auto-export failed after daily summary for '{agent_id}': {e}"
            )
            export_result = {"status": "error", "error": str(e)}

        return {
            "summary": summary_result,
            "export": export_result,
        }

    def generate_conflict_report(self, agent_id: str, date: str) -> dict[str, Any]:
        """
        Generate the conflict report for an agent/date.

        Runs the LLM conflict-detection pass over the day's session
        memories and writes the JSON report to ``~/.memanto/conflicts/``.

        Args:
            agent_id: Target agent.
            date: Date string (YYYY-MM-DD).

        Returns:
            Dict with ``conflicts`` sub-result.
        """
        # Ensure agent exists
        self.get_agent(agent_id)

        logger.debug(
            "Generating conflict report for agent '%s' on %s",
            agent_id,
            date,
        )

        service = self._get_daily_analysis_service()
        conflict_result = service.generate_conflict_report(agent_id, date)
        return {"conflicts": conflict_result}

    # Conflict Resolution

    def list_conflicts(
        self, agent_id: str, date: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Load unresolved conflicts from the JSON conflict report.

        Args:
            agent_id: Target agent.
            date: Date string (YYYY-MM-DD). Defaults to today.

        Returns:
            List of unresolved conflict dicts.
        """

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        json_path = (
            Path.home() / ".memanto" / "conflicts" / f"{agent_id}_{date}_conflicts.json"
        )

        if not json_path.exists():
            return []

        with open(json_path, encoding="utf-8") as f:
            all_conflicts = json.load(f)

        # Return only unresolved conflicts
        return [c for c in all_conflicts if not c.get("resolved", False)]

    def resolve_conflict(
        self,
        agent_id: str,
        date: str,
        conflict_index: int,
        action: str,
        manual_content: str | None = None,
        manual_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Resolve a single conflict by index.

        Args:
            agent_id: Target agent.
            date: Date string (YYYY-MM-DD).
            conflict_index: 0-based index into the full conflicts list.
            action: Resolution action — ``keep_old``, ``keep_new``,
                ``keep_both``, ``remove_both``, or ``manual``.
            manual_content: Required when action is ``manual``.
            manual_type: Memory type for manual replacement (default: old memory's type).

        Returns:
            Dict with resolution result.
        """

        valid_actions = {"keep_old", "keep_new", "keep_both", "remove_both", "manual"}
        if action not in valid_actions:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid_actions))}"
            )

        json_path = (
            Path.home() / ".memanto" / "conflicts" / f"{agent_id}_{date}_conflicts.json"
        )
        if not json_path.exists():
            raise ValueError(f"No conflict report found for {agent_id} on {date}")

        with open(json_path, encoding="utf-8") as f:
            all_conflicts = json.load(f)

        if conflict_index < 0 or conflict_index >= len(all_conflicts):
            raise ValueError(
                f"Conflict index {conflict_index} out of range (0-{len(all_conflicts) - 1})"
            )

        conflict = all_conflicts[conflict_index]
        old_id = conflict.get("old_memory_id")
        new_id = conflict.get("new_memory_id")

        # Get namespace for memory operations
        from memanto.app.core import agent_namespace

        namespace = agent_namespace(agent_id)

        write_service = self._get_write_service()
        result_details = {"action": action}

        if action == "keep_old":
            # Keep old, delete new
            if new_id:
                try:
                    write_service.delete_memory(new_id, namespace)
                    result_details["deleted"] = new_id
                except Exception as e:
                    result_details["warning"] = f"Could not delete new memory: {e}"

        elif action == "keep_new":
            # Keep new, delete old
            if old_id:
                try:
                    write_service.delete_memory(old_id, namespace)
                    result_details["deleted"] = old_id
                except Exception as e:
                    result_details["warning"] = f"Could not delete old memory: {e}"

        elif action == "keep_both":
            # No-op — both memories remain active
            result_details["note"] = "Both memories kept as-is"

        elif action == "remove_both":
            # Delete both memories
            for mem_id, label in [(old_id, "old"), (new_id, "new")]:
                if mem_id:
                    try:
                        write_service.delete_memory(mem_id, namespace)
                        result_details[f"deleted_{label}"] = mem_id
                    except Exception as e:
                        result_details[f"warning_{label}"] = (
                            f"Could not delete {label} memory: {e}"
                        )

        elif action == "manual":
            if not manual_content:
                raise ValueError("manual_content is required when action is 'manual'")

            # Delete both, store manual replacement
            for mem_id, label in [(old_id, "old"), (new_id, "new")]:
                if mem_id:
                    try:
                        write_service.delete_memory(mem_id, namespace)
                        result_details[f"deleted_{label}"] = mem_id
                    except Exception as e:
                        result_details[f"warning_{label}"] = (
                            f"Could not delete {label} memory: {e}"
                        )

            # Store the manual replacement
            mem_type = manual_type or conflict.get("type", "fact")
            if not isinstance(mem_type, str):
                mem_type = "fact"
            # Map conflict types to valid memory types
            if mem_type not in _VALID_MEMORY_TYPES:
                mem_type = "fact"
            resolved_type = cast(MemoryType, mem_type)

            from memanto.app.core import MemoryRecord

            title = (
                manual_content[:47] + "..."
                if len(manual_content) > 50
                else manual_content
            )
            memory = MemoryRecord(
                type=resolved_type,
                title=title,
                content=manual_content,
                agent_id=agent_id,
                actor_id=agent_id,
                confidence=0.9,
                tags=["conflict-resolution"],
                source="user",
                provenance="corrected",
            )
            store_result = write_service.store_memory(memory)
            result_details["new_memory_id"] = store_result.get("id")

        # Mark conflict as resolved in the JSON file
        all_conflicts[conflict_index]["resolved"] = True
        all_conflicts[conflict_index]["resolution"] = action
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_conflicts, f, indent=2, default=str)

        result_details["status"] = "resolved"
        return result_details

    # Memory Export

    def export_memory_md(
        self,
        agent_id: str,
        output_path: str | None = None,
        limit_per_type: int = 25,
    ) -> dict[str, Any]:
        """
        Export all memories for an agent into a structured memory.md.

        Queries each of the 13 memory types and generates a Markdown file
        organized by type.

        Args:
            agent_id: Target agent.
            output_path: Custom output path. Defaults to
                ``~/.memanto/exports/{agent_id}_memory.md``.
            limit_per_type: Max memories per type (default 25).

        Returns:
            Dict with ``output_path``, ``total_memories``, ``per_type_counts``.
        """
        # Ensure there is a valid, non-expired session for this agent
        self._get_validated_session_for_agent(agent_id)

        from memanto.app.services.memory_export_service import MEMORY_TYPE_ORDER

        memories_by_type: dict[str, list] = {}

        for mem_type in MEMORY_TYPE_ORDER:
            try:
                result = self.recall(
                    agent_id=agent_id,
                    query="*",
                    limit=limit_per_type,
                    type=[mem_type],
                )
                memories_by_type[mem_type] = result.get("memories", [])
            except Exception:
                memories_by_type[mem_type] = []

        export_svc = self._get_export_service()
        out = output_path if output_path else None
        written_path = export_svc.write_memory_md(
            agent_id=agent_id,
            memories_by_type=memories_by_type,
            output_path=Path(out) if out else None,
        )

        per_type_counts = {t: len(mems) for t, mems in memories_by_type.items() if mems}
        total = sum(per_type_counts.values())

        return {
            "output_path": str(written_path),
            "total_memories": total,
            "per_type_counts": per_type_counts,
        }

    def sync_memory_to_project(
        self,
        agent_id: str,
        project_dir: str,
        limit_per_type: int = 25,
    ) -> dict[str, Any]:
        """
        Sync agent memories to a project directory's MEMORY.md.

        Uses the cached export at ``~/.memanto/exports/{agent_id}_memory.md``
        when available. Falls back to a fresh export if
        the cache file does not exist.

        Args:
            agent_id: Target agent.
            project_dir: Path to the project directory.
            limit_per_type: Max memories per type for fresh export (default 25).

        Returns:
            Dict with ``output_path``, ``total_memories``, ``source``
            (``"cache"`` or ``"fresh"``).
        """

        cache_path = Path.home() / ".memanto" / "exports" / f"{agent_id}_memory.md"
        target_path = Path(project_dir) / "MEMORY.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if cache_path.exists():
            # Fast path: copy cached export
            shutil.copy2(str(cache_path), str(target_path))
            # Count memories from the cached file
            content = cache_path.read_text(encoding="utf-8")
            mem_count = content.count("### ")
            return {
                "output_path": str(target_path.resolve()),
                "total_memories": mem_count,
                "source": "cache",
            }

        # Fallback: run a fresh export to the default location, then copy
        logger.debug(
            "No cached export found, generating fresh export for '%s'", agent_id
        )
        export_result = self.export_memory_md(
            agent_id=agent_id,
            limit_per_type=limit_per_type,
        )

        # Now copy the freshly generated export to the project
        exported_path = Path(export_result["output_path"])
        if exported_path.exists():
            shutil.copy2(str(exported_path), str(target_path))

        return {
            "output_path": str(target_path.resolve()),
            "total_memories": export_result.get("total_memories", 0),
            "source": "fresh",
        }

    # Health Check
    def health_check(self) -> dict[str, Any]:
        """
        Health check — not applicable in direct mode.

        Direct mode bypasses the local server entirely. This method
        exists only for interface compatibility with ``MemantoAPIClient``.

        Raises:
            ConnectionError: Always, to signal server unavailability.
        """
        raise ConnectionError(
            "Direct mode does not use a local server. "
            "Run 'memanto serve' to start the server if needed."
        )

    # Input validators

    @staticmethod
    def _validate_memory_input(
        memory_type: str | None,
        title: str,
        content: str,
        confidence: float,
    ) -> None:
        """Validate memory fields before sending to service layer."""
        if memory_type is not None and memory_type not in _VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{memory_type}'. "
                f"Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}"
            )
        if not content or not content.strip():
            raise ValueError("Memory content must be a non-empty string")
        if len(content) > _MAX_CONTENT_LENGTH:
            raise ValueError(f"Memory content exceeds {_MAX_CONTENT_LENGTH} characters")
        if title and len(title) > _MAX_TITLE_LENGTH:
            raise ValueError(f"Memory title exceeds {_MAX_TITLE_LENGTH} characters")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {confidence}"
            )

    @staticmethod
    def _validate_query(query: str, limit: int) -> None:
        """Validate search parameters."""
        if not query or not query.strip():
            raise ValueError("Search query must be a non-empty string")
        if not 1 <= limit <= 100:
            raise ValueError(f"Limit must be between 1 and 100, got {limit}")

"""
MEMANTO Hosted Client

Talks to the hosted Memanto Cloud API (``memanto-cloud`` backend) over HTTP.

``HostedClient`` subclasses ``SdkClient`` so every caller (CLI commands,
hooks, memanto-mcp) keeps one interface. Memory logic runs server-side: each
storage method below is overridden to call the public gateway. What is still
inherited is local-only by design:

* the active-agent record (``SessionService`` under ``~/.memanto/sessions``),
  which the CLI uses to know which agent is active - nothing is sent to the
  server for it;
* MEMORY.md / OKF export and project sync, which render the results of
  ``recall`` into local files;
* the static policy preset catalogue.

The Moorcheh client and the local agent registry are blocked: if an
un-overridden path ever reaches them, it fails loudly instead of silently
using a different store.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, cast

import httpx

from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AuthenticationError,
    AuthorizationError,
    MemoryOperationError,
)
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import (
    DEFAULT_MEMANTO_API_URL,
    MEMANTO_CONSOLE_URL,
    ConfigManager,
)

logger = logging.getLogger(__name__)

__all__ = ["HostedClient"]

_TIMEOUT_SECONDS = 30.0
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
# Retried: rate limiting and gateway errors where the request did not reach a
# service. A plain 500 or a read timeout is not retried, so a write that may
# have been applied is never sent twice.
_RETRY_STATUSES = {429, 502, 503, 504}
_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".json", ".txt", ".csv", ".md"}


def _not_available(what: str) -> NoReturn:
    raise MemoryOperationError(f"Not available on Memanto Cloud yet: {what}")


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so the server applies its own defaults."""
    return {k: v for k, v in data.items() if v is not None}


class HostedClient(SdkClient):
    """HTTP client for the Memanto Cloud public API (``x-api-key`` auth)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_MEMANTO_API_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Args:
            api_key: Memanto Cloud key (``mk_...``).
            base_url: Public gateway URL.
            transport: Optional httpx transport (tests inject a mock here).
        """
        super().__init__(api_key)
        from memanto.app import __version__

        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
            headers={
                "x-api-key": api_key,
                "User-Agent": f"memanto-cli/{__version__}",
            },
        )

    # Blocked local backends

    def _get_moorcheh(self):
        _not_available("this operation (it needs a local Moorcheh client)")

    def _get_agent_service(self):
        _not_available("this operation (it needs the local agent registry)")

    # HTTP

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one request; retry rate limits and gateway errors; map failures."""
        response = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise ConnectionError(
                    f"Could not reach Memanto Cloud at {self.base_url}: {e}"
                ) from e
            except httpx.TransportError as e:
                raise ConnectionError(f"Memanto Cloud request failed: {e}") from e

            if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            break

        assert response is not None
        if response.is_success:
            return cast(dict[str, Any], response.json()) if response.content else {}
        self._raise_for_status(response)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or f"HTTP {response.status_code}"
        if isinstance(body, dict):
            for key in ("message", "error", "detail"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        return f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> NoReturn:
        status = response.status_code
        message = self._error_message(response)
        if status == 401:
            raise AuthenticationError(
                f"Memanto Cloud rejected the API key ({message}). Run: memanto login"
            )
        if status == 402 or (status == 429 and "limit" in message.lower()):
            raise MemoryOperationError(
                f"Memanto Cloud plan limit reached: {message}. "
                f"Upgrade at {MEMANTO_CONSOLE_URL}/billing"
            )
        if status == 403:
            raise AuthorizationError(message)
        if status == 409:
            raise AgentAlreadyExistsError(message)
        if status in (400, 404, 422):
            raise ValueError(message)
        if status >= 500 or status == 429:
            raise ConnectionError(f"Memanto Cloud error (HTTP {status}): {message}")
        raise MemoryOperationError(f"Memanto Cloud error (HTTP {status}): {message}")

    @staticmethod
    def _agent_path(agent_id: str, suffix: str = "") -> str:
        from urllib.parse import quote

        return f"/agents/{quote(agent_id, safe='')}{suffix}"

    # Account

    def get_account(self) -> dict[str, Any] | None:
        """Return ``GET /me`` (user, email, plan, usage), or None if the server has no ``/me`` yet."""
        try:
            return self._request("GET", "/me")
        except ValueError:
            return None

    # Agent Management

    def create_agent(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create an agent on Memanto Cloud."""
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        return self._request(
            "POST",
            "/agents",
            json=_compact(
                {"agent_id": agent_id, "pattern": pattern, "description": description}
            ),
        )

    def list_agents(self) -> dict[str, Any]:
        """List agents: ``{agents, count, warnings}``."""
        return self._request("GET", "/agents")

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get one agent. Raises ``AgentNotFoundError`` when it does not exist."""
        try:
            return self._request("GET", self._agent_path(agent_id))
        except ValueError as e:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found") from e

    def delete_agent(
        self, agent_id: str, delete_memories: bool = False
    ) -> dict[str, Any]:
        """Delete an agent. Memanto Cloud always deletes its memories with it."""
        if not delete_memories:
            raise ValueError(
                "Memanto Cloud deletes an agent's memories together with the agent; "
                "they cannot be kept. Pass delete_memories=True (--delete-memories)."
            )
        session_service = self._get_session_service()
        with session_service.lock_agent_lifecycle(agent_id):
            self.get_agent(agent_id)
            self._request("DELETE", self._agent_path(agent_id))
            session_service.delete_session(agent_id)
        if self.agent_id == agent_id:
            self.session_token = None
            self.agent_id = None
            self._cached_session = None
        return {"status": "deleted", "agent_id": agent_id, "memories_deleted": True}

    # Session Management (local active-agent record; nothing server-side)

    def activate_agent(
        self, agent_id: str, duration_hours: int | None = None
    ) -> dict[str, Any]:
        """Check the agent exists on Memanto Cloud and record it as active locally."""
        from memanto.app.models.session import AgentPattern

        agent = self.get_agent(agent_id)
        pattern = agent.get("pattern")
        session = self._get_session_service().create_session(
            agent_id=agent_id,
            pattern=AgentPattern(pattern) if pattern else None,
            duration_hours=duration_hours,
        )
        self.session_token = session.session_token
        self.agent_id = agent_id
        self._cached_session = session
        return {
            "session_token": session.session_token,
            "session_id": session.session_id,
            "agent_id": agent_id,
            "namespace": session.namespace,
            "expires_at": session.expires_at.isoformat(),
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
        """Store one memory."""
        self._get_validated_session_for_agent(agent_id)
        self._validate_memory_input(memory_type, title, content, confidence)
        result = self._request(
            "POST",
            self._agent_path(agent_id, "/remember"),
            json=_compact(
                {
                    "type": memory_type,
                    "title": title or None,
                    "content": content,
                    "confidence": confidence,
                    "tags": tags or [],
                    "source": source,
                    "provenance": provenance,
                }
            ),
        )
        return {
            "memory_id": result.get("memory_id"),
            "agent_id": agent_id,
            "namespace": agent_id,
            "status": result.get("status", "queued"),
            "confidence": result.get("confidence", confidence),
            "type": result.get("type"),
        }

    def batch_remember(
        self,
        agent_id: str,
        memories: list[dict[str, Any]],
        source: str | None = None,
    ) -> dict[str, Any]:
        """Store up to 100 memories: ``{total_submitted, successful, failed, results}``."""
        self._get_validated_session_for_agent(agent_id)
        if not memories:
            raise ValueError("Batch must contain at least one memory")
        if len(memories) > 100:
            raise ValueError(f"Batch size {len(memories)} exceeds maximum of 100")
        return self._request(
            "POST",
            self._agent_path(agent_id, "/batch-remember"),
            json=_compact({"memories": memories, "source": source}),
        )

    def update_memory(
        self, agent_id: str, memory_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update fields of one memory."""
        self._get_validated_session_for_agent(agent_id)
        if not updates:
            raise ValueError("Provide at least one field to update")
        result = self._request(
            "PATCH",
            self._agent_path(agent_id, f"/memories/{memory_id}"),
            json=updates,
        )
        return {"namespace": agent_id, **result}

    def extract_memories_from_conversation(
        self,
        agent_id: str,
        messages: list[dict[str, str]],
        dry_run: bool = False,
        max_memories: int = 20,
        ai_model: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Extract typed memories from conversation turns (server-side)."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST",
            self._agent_path(agent_id, "/remember/extract"),
            json=_compact(
                {
                    "messages": messages,
                    "dry_run": dry_run,
                    "max_memories": max_memories,
                    "ai_model": ai_model,
                    "source": source,
                }
            ),
        )

    def delete_memory(self, agent_id: str, memory_id: str) -> dict[str, Any]:
        """Delete one memory."""
        self._get_validated_session_for_agent(agent_id)
        self._request("DELETE", self._agent_path(agent_id, f"/memories/{memory_id}"))
        return {
            "status": "deleted",
            "agent_id": agent_id,
            "memory_id": memory_id,
            "namespace": agent_id,
        }

    def expire_memory(
        self, agent_id: str, memory_id: str, reason: str = "manual"
    ) -> dict[str, Any]:
        """Expire one memory (reversible)."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST",
            self._agent_path(agent_id, f"/memories/{memory_id}/expire"),
            json={"reason": reason},
        )

    def restore_memory(self, agent_id: str, memory_id: str) -> dict[str, Any]:
        """Return an expired memory to active."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST",
            self._agent_path(agent_id, f"/memories/{memory_id}/restore"),
            json={},
        )

    # Expiry policies

    def get_policy(self, agent_id: str) -> dict[str, Any]:
        """Return the agent's expiry policy."""
        self._get_validated_session_for_agent(agent_id)
        return self._request("GET", self._agent_path(agent_id, "/policy"))

    def set_policy(self, agent_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        """Replace the agent's expiry policy."""
        self._get_validated_session_for_agent(agent_id)
        return self._request("PUT", self._agent_path(agent_id, "/policy"), json=policy)

    def apply_policy_preset(self, agent_id: str, name: str) -> dict[str, Any]:
        """Adopt a predefined policy bundle."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST", self._agent_path(agent_id, "/policy/preset"), json={"name": name}
        )

    def apply_policy(self, agent_id: str, dry_run: bool = False) -> dict[str, Any]:
        """Expire every memory the policy matches."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST",
            self._agent_path(agent_id, "/policy/apply"),
            json={"dry_run": dry_run},
        )

    def purge_expired(self, agent_id: str, dry_run: bool = False) -> dict[str, Any]:
        """Permanently delete memories expired past the purge window."""
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST",
            self._agent_path(agent_id, "/policy/purge"),
            json={"dry_run": dry_run},
        )

    def upload_file(self, agent_id: str, file_path: str) -> dict[str, Any]:
        """Upload a file: create a tracked file, then PUT its bytes to the signed URL."""
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File not found: {file_path}")
        suffix = path.suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
            allowed_str = ", ".join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))
            raise ValueError(
                f"File type '{suffix}' is not supported. Allowed types: {allowed_str}"
            )
        self._get_validated_session_for_agent(agent_id)

        size = path.stat().st_size
        created = self._request(
            "POST",
            self._agent_path(agent_id, "/files"),
            json={"file_name": path.name, "size_bytes": size},
        )
        upload = httpx.put(
            created["upload_url"],
            content=path.read_bytes(),
            headers={
                "Content-Type": created.get("content_type")
                or "application/octet-stream"
            },
            timeout=None,
        )
        if not upload.is_success:
            raise MemoryOperationError(
                f"File upload to storage failed (HTTP {upload.status_code})"
            )
        return {
            "agent_id": agent_id,
            "namespace": agent_id,
            "success": True,
            "message": f"Upload queued for processing (job {created.get('job_id')})",
            "file_name": created.get("file_name", path.name),
            "file_size": size,
            "file_id": created.get("file_id"),
            "job_id": created.get("job_id"),
        }

    # Recall

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_similarity: float | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        min_confidence: float | None = None,
        status: str = "all",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Semantic recall: ``{agent_id, query, memories, count}``."""
        recall_cfg = ConfigManager().get_recall_config()
        if limit is None:
            limit = recall_cfg["limit"]
        if min_similarity is None:
            min_similarity = recall_cfg.get("min_similarity")
        self._get_validated_session_for_agent(agent_id)
        self._validate_query(query, limit)

        result = self._request(
            "POST",
            self._agent_path(agent_id, "/recall"),
            json=_compact(
                {
                    "query": query,
                    "limit": limit,
                    "type": type,
                    "tags": tags,
                    "min_similarity": min_similarity,
                    "created_after": created_after.isoformat()
                    if created_after
                    else None,
                    "created_before": created_before.isoformat()
                    if created_before
                    else None,
                    "min_confidence": min_confidence,
                    "status": status,
                    "source": source,
                }
            ),
        )
        return {
            "agent_id": agent_id,
            "query": query,
            "memories": result.get("memories", []),
            "count": result.get("count", 0),
        }

    def _temporal_recall(
        self, agent_id: str, route: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        from memanto.app.utils.validation import validate_recall_limit

        if body.get("limit") is None:
            body["limit"] = ConfigManager().get_recall_config()["limit"]
        validate_recall_limit(body["limit"])
        self._get_validated_session_for_agent(agent_id)
        return self._request(
            "POST", self._agent_path(agent_id, f"/recall/{route}"), json=_compact(body)
        )

    def recall_as_of(
        self,
        agent_id: str,
        as_of: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Point-in-time recall."""
        result = self._temporal_recall(
            agent_id,
            "as-of",
            {
                "as_of": as_of,
                "limit": limit,
                "type": type,
                "tags": tags,
                "source": source,
            },
        )
        return {
            "agent_id": agent_id,
            "as_of_date": as_of,
            "memories": result.get("memories", []),
            "count": result.get("count", 0),
        }

    def recall_changed_since(
        self,
        agent_id: str,
        since: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        status: str = "all",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Memories created or changed since a date."""
        result = self._temporal_recall(
            agent_id,
            "changed-since",
            {
                "since": since,
                "limit": limit,
                "type": type,
                "tags": tags,
                "status": status,
                "source": source,
            },
        )
        return {
            "agent_id": agent_id,
            "since_date": since,
            "memories": result.get("memories", []),
            "count": result.get("count", 0),
        }

    def recall_recent(
        self,
        agent_id: str,
        limit: int | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        status: str = "all",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Most recent memories, newest first."""
        result = self._temporal_recall(
            agent_id,
            "recent",
            {
                "limit": limit,
                "type": type,
                "tags": tags,
                "status": status,
                "source": source,
            },
        )
        return {
            "agent_id": agent_id,
            "memories": result.get("memories", []),
            "count": result.get("count", 0),
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
        source: str | None = None,
    ) -> dict[str, Any]:
        """Answer a question from the agent's memories (server-side RAG)."""
        ans_cfg = ConfigManager().get_answer_config()
        if limit is None:
            limit = ans_cfg["answer_limit"]
        if temperature is None:
            temperature = ans_cfg["temperature"]
        if kiosk_mode is None:
            kiosk_mode = bool(ans_cfg.get("kiosk_mode", False))
        if kiosk_mode and threshold is None:
            threshold = ans_cfg["threshold"]
        # The local default model names a Moorcheh model; Memanto Cloud picks
        # its own default unless the caller names one explicitly.
        self._get_validated_session_for_agent(agent_id)
        if not question or not question.strip():
            raise ValueError("Question must be a non-empty string")

        result = self._request(
            "POST",
            self._agent_path(agent_id, "/answer"),
            json=_compact(
                {
                    "question": question,
                    "limit": limit,
                    "threshold": threshold,
                    "temperature": temperature,
                    "ai_model": ai_model,
                    "kiosk_mode": kiosk_mode,
                    "header_prompt": header_prompt,
                    "footer_prompt": footer_prompt,
                    "source": source,
                    "stream": False,
                }
            ),
        )
        return {
            "agent_id": agent_id,
            "question": question,
            "answer": result.get("answer", "No answer generated."),
            "sources": result.get("sources", []),
            "namespace": agent_id,
        }

    # Daily summary and conflicts (generated and stored server-side)

    def generate_daily_summary(
        self, agent_id: str, date: str, output_path: str | None = None
    ) -> dict[str, Any]:
        """Generate the daily summary on Memanto Cloud; optionally save it locally."""
        result = self._request(
            "POST", self._agent_path(agent_id, "/daily-summary"), json={"date": date}
        )
        summary = result.get("summary", {})
        if output_path and summary.get("status") == "success":
            stored = self._request(
                "GET",
                self._agent_path(agent_id, "/daily-summary"),
                params={"date": date},
            )
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(stored.get("content", ""), encoding="utf-8")
            summary = {**summary, "summary_path": str(out)}

        try:
            export_result = self.export_memory_md(agent_id)
        except Exception as e:
            logger.warning(
                f"Auto-export failed after daily summary for '{agent_id}': {e}"
            )
            export_result = {"status": "error", "error": str(e)}
        return {"summary": summary, "export": export_result}

    def generate_conflict_report(
        self, agent_id: str, date: str, on_progress=None, cancel_event=None
    ) -> dict[str, Any]:
        """Run conflict detection on Memanto Cloud for one day."""
        result = self._request(
            "POST",
            self._agent_path(agent_id, "/conflicts/generate"),
            json={"date": date},
        )
        return {"conflicts": result.get("conflicts", {})}

    def list_conflicts(
        self, agent_id: str, date: str | None = None
    ) -> list[dict[str, Any]]:
        """Unresolved conflicts for one day, each with its stable ``index``."""
        from memanto.app.utils.temporal_helpers import utc_date_str

        result = self._request(
            "GET",
            self._agent_path(agent_id, "/conflicts"),
            params={"date": date or utc_date_str()},
        )
        return cast(list[dict[str, Any]], result.get("conflicts", []))

    def resolve_conflict(
        self,
        agent_id: str,
        date: str,
        conflict_index: int,
        action: str,
        manual_content: str | None = None,
        manual_type: str | None = None,
    ) -> dict[str, Any]:
        """Resolve one conflict by its ``index``."""
        return self._request(
            "POST",
            self._agent_path(agent_id, "/conflicts/resolve"),
            json=_compact(
                {
                    "date": date,
                    "conflict_index": conflict_index,
                    "action": action,
                    "manual_content": manual_content,
                    "manual_type": manual_type,
                }
            ),
        )

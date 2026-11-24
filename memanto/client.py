"""
Memanto Python client.

A single-agent client that runs in-process — no server to start. It resolves
credentials from the environment or ``~/.memanto`` (or runs keyless on the
on-prem backend), creates the agent on first use, and reuses the agent's live
session instead of activating a new one.

    from memanto import Memanto

    memanto = Memanto(agent_id="my-agent")
    memanto.remember("Alex prefers oat milk.")
    memanto.recall("what does Alex drink?")
    memanto.answer("Does Alex drink dairy?")

Every method returns the same dict shape as the matching REST endpoint. For
operations not wrapped here, use the underlying ``SdkClient`` via
:attr:`Memanto.client`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

from memanto.app.utils.client_identity import calling_tool, tool_from_source
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
)
from memanto.cli.client.sdk_client import SdkClient

_ORIG_SDK_CLIENT = SdkClient

__all__ = ["Memanto"]

_T = TypeVar("_T")

# Placeholder key for the on-prem backend; OnPremClient ignores it.
_ON_PREM_API_KEY = "on-prem"

# Raised when this instance's session lapsed or another client of the same
# agent replaced it. SdkClient checks the session before any side effect, so
# re-establishing the session and retrying once cannot duplicate a write.
_SESSION_ERRORS = (SessionExpiredError, InvalidSessionTokenError, SessionNotFoundError)


def _as_list(value: str | list[str] | None) -> list[str] | None:
    """Accept a single filter value as well as a list (``type="fact"``)."""
    return [value] if isinstance(value, str) else value


def _is_cloud_api_key(key: str) -> bool:
    clean = key.strip()
    if not clean:
        return False
    if clean.startswith("mk_"):
        return True
    env_cloud = os.environ.get("MEMANTO_API_KEY", "").strip()
    return bool(env_cloud and clean == env_cloud)


def _resolve_credentials(api_key: str | None) -> tuple[str, bool]:
    """Return ``(key, is_cloud)`` from explicit arg, ``MEMANTO_API_KEY``, ``~/.memanto``, or ``MOORCHEH_API_KEY``.

    Importing ``memanto.app.config`` loads ``~/.memanto/.env`` over the
    environment, so a key saved by ``memanto`` setup is available alongside
    exported environment variables. The on-prem backend needs no key.
    """
    from memanto.app.clients.backend import Backend
    from memanto.app.config import settings
    from memanto.cli.config.manager import ConfigManager

    if api_key is not None and api_key.strip():
        clean = api_key.strip()
        is_cloud = _is_cloud_api_key(clean)
        if not is_cloud and not settings.MOORCHEH_API_KEY:
            settings.MOORCHEH_API_KEY = clean
        return clean, is_cloud

    memanto_key = os.environ.get("MEMANTO_API_KEY", "").strip()
    if memanto_key:
        return memanto_key, True

    config = ConfigManager()
    backend = config.get_backend()
    if backend == Backend.MEMANTO_CLOUD:
        cloud_key = config.get_memanto_api_key()
        if cloud_key and cloud_key.strip():
            return cloud_key.strip(), True

    if api_key is None and backend == Backend.ON_PREM:
        return _ON_PREM_API_KEY, False

    key = os.environ.get("MOORCHEH_API_KEY") or config.get_api_key()
    if not key or not key.strip():
        raise ValueError(
            "No Memanto API key (or Moorcheh API key) found. Pass api_key=..., "
            "set MEMANTO_API_KEY (https://console.memanto.ai/sign-in) or MOORCHEH_API_KEY, "
            "or run `memanto login`."
        )
    # Services that fall back to the global key (daily analysis) need one. Fill
    # it only when none is configured: never replace the key that other
    # clients in this process resolve.
    if not settings.MOORCHEH_API_KEY:
        settings.MOORCHEH_API_KEY = key
    return key, False


def _resolve_api_key(api_key: str | None) -> str:
    """Return the key to use: explicit arg, ``MEMANTO_API_KEY``, ``~/.memanto``, or ``MOORCHEH_API_KEY``."""
    key, _ = _resolve_credentials(api_key)
    return key


def _instantiate_sdk_client(
    key: str,
    *,
    explicit_api_key: str | None = None,
    is_cloud: bool | None = None,
) -> SdkClient:
    """Construct ``HostedClient`` for Memanto Cloud keys, else ``SdkClient``."""
    if SdkClient is not _ORIG_SDK_CLIENT:
        return SdkClient(api_key=key)

    from memanto.app.clients.backend import Backend
    from memanto.cli.client.hosted_client import HostedClient
    from memanto.cli.config.manager import ConfigManager

    config = ConfigManager()
    if is_cloud is not None:
        use_cloud = is_cloud
    else:
        saved_cloud_key = (
            (config.get_memanto_api_key() or "").strip()
            if explicit_api_key is None
            and config.get_backend() == Backend.MEMANTO_CLOUD
            else ""
        )
        use_cloud = _is_cloud_api_key(key) or (
            bool(saved_cloud_key) and key.strip() == saved_cloud_key
        )

    if use_cloud:
        base_url = (
            os.environ.get("MEMANTO_API_URL", "").strip()
            or config.get_memanto_api_url()
        )
        return HostedClient(key, base_url=base_url)

    return SdkClient(api_key=key)


class Memanto:
    """Memory client bound to one Memanto agent.

    Args:
        agent_id: Agent to read and write (alphanumeric, ``-`` and ``_``).
        api_key: Memanto Cloud API key (``mk_...``) or Moorcheh API key.
            Defaults to ``MEMANTO_API_KEY``, the active ``~/.memanto`` sign-in
            (``memanto login``), or ``MOORCHEH_API_KEY``; not needed on the
            on-prem backend.
        auto_create: Create the agent if it does not exist (default ``True``).
        pattern: Pattern for an auto-created agent — ``"tool"`` (default),
            ``"support"``, or ``"project"``.
        session_hours: Lifetime of a newly activated session. Defaults to the
            configured session duration.

    Raises:
        ValueError: If no API key can be resolved, or *agent_id* is invalid.
        AgentNotFoundError: If the agent does not exist and *auto_create* is
            ``False``.

    Memanto allows one session per agent: activating a session signs out every
    other client of that agent. So the client adopts the agent's live session
    when there is one and only activates when there is none — at construction,
    and again whenever its session expires or another client (the CLI, another
    process) replaces it. Use one instance per agent; an instance is not
    thread-safe.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        api_key: str | None = None,
        auto_create: bool = True,
        pattern: str = "tool",
        session_hours: int | None = None,
    ) -> None:
        self.agent_id = agent_id
        resolved_key = _resolve_api_key(api_key)
        self.client = _instantiate_sdk_client(resolved_key, explicit_api_key=api_key)
        self._session_hours = session_hours
        self._ensure_agent(auto_create, pattern)
        self._ensure_session()

    def _ensure_agent(self, auto_create: bool, pattern: str) -> None:
        try:
            self.client.get_agent(self.agent_id)
            return
        except AgentNotFoundError:
            if not auto_create:
                raise
        try:
            self.client.create_agent(self.agent_id, pattern=pattern)
        except AgentAlreadyExistsError:
            pass  # created concurrently by another client

    def _ensure_session(self) -> None:
        """Adopt the agent's live session if its token verifies, else activate."""
        from memanto.app.services.session_service import get_session_service

        service = get_session_service()
        session = service.get_session(self.agent_id)
        if session is not None and session.is_active():
            try:
                service.validate_session(session.session_token)
            except (SessionExpiredError, InvalidSessionTokenError):
                pass  # e.g. signed with a rotated secret key; activate below
            else:
                self.client.session_token = session.session_token
                self.client.agent_id = self.agent_id
                # Drop SdkClient's cached session so it re-validates the new token.
                self.client._cached_session = None
                return
        self.client.activate_agent(self.agent_id, duration_hours=self._session_hours)

    def _call(self, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        """Run an SdkClient call, recovering once from a lost session."""
        try:
            return fn(self.agent_id, *args, **kwargs)
        except _SESSION_ERRORS:
            self._ensure_session()
            return fn(self.agent_id, *args, **kwargs)

    # Write

    def remember(
        self,
        content: str,
        *,
        type: str | None = None,
        title: str | None = None,
        confidence: float = 0.8,
        tags: str | list[str] | None = None,
        source: str = "user",
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """Store one memory. *title* defaults to the start of *content*.

        Returns a dict with ``memory_id``, ``status``, ``type``, etc.
        """
        if title is None:
            title = f"{content[:50]}..." if len(content) > 50 else content
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.remember,
                memory_type=type,
                title=title,
                content=content,
                confidence=confidence,
                tags=_as_list(tags),
                source=source,
                provenance=provenance,
            )

    def batch_remember(
        self, memories: list[dict[str, Any]], *, source: str | None = None
    ) -> dict[str, Any]:
        """Store up to 100 memories. Each item takes the same keys as
        :meth:`remember` (``content`` required)."""
        batch_tool = tool_from_source(source)
        if not batch_tool:
            for item in memories:
                if isinstance(item, dict):
                    batch_tool = tool_from_source(item.get("source"))
                    if batch_tool:
                        break
        if source:
            memories = [
                {**item, "source": item.get("source") or source}
                if isinstance(item, dict)
                else item
                for item in memories
            ]
        with calling_tool(batch_tool):
            return self._call(self.client.batch_remember, memories)

    def extract(
        self,
        messages: list[dict[str, str]],
        *,
        dry_run: bool = False,
        max_memories: int = 20,
        ai_model: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Extract typed memories from chat turns and store them.

        *messages* are ``{"role": ..., "content": ...}`` dicts. With
        ``dry_run=True`` the candidates are returned without being stored.

        Returns a dict with the ``candidates`` and, unless ``dry_run``, the
        batch result (``successful``, ``failed``, ``results``, ...).

        Raises:
            NothingToExtractError: If the conversation held nothing worth
                remembering (a ``ValueError``; importable from ``memanto``).
        """
        extra: dict[str, Any] = {}
        if source is not None:
            extra["source"] = source
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.extract_memories_from_conversation,
                messages,
                dry_run=dry_run,
                max_memories=max_memories,
                ai_model=ai_model,
                **extra,
            )

    def update_memory(self, memory_id: str, **updates: Any) -> dict[str, Any]:
        """Update fields of a memory, e.g. ``content=...`` or ``tags=[...]``."""
        return self._call(self.client.update_memory, memory_id, updates)

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by id."""
        return self._call(self.client.delete_memory, memory_id)

    def delete_agent(self, *, delete_memories: bool = False) -> dict[str, Any]:
        """Delete this agent; the instance cannot be used afterwards.

        By default the agent's memories stay in Moorcheh and come back if an
        agent with the same id is created again. Pass ``delete_memories=True``
        to delete them permanently as well. If that fails, the agent is left
        intact and ``NamespaceError`` is raised, so the call can be retried.
        """
        return self.client.delete_agent(self.agent_id, delete_memories=delete_memories)

    # Read
    #
    # ``type`` and ``tags`` filters take one value or a list of values.

    def recall(
        self,
        query: str,
        *,
        limit: int | None = None,
        type: str | list[str] | None = None,
        tags: str | list[str] | None = None,
        min_similarity: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Semantic search over this agent's memories.

        Returns a dict whose ``memories`` list is ranked by relevance.
        """
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.recall,
                query,
                limit=limit,
                type=_as_list(type),
                tags=_as_list(tags),
                min_similarity=min_similarity,
            )

    def recall_as_of(
        self,
        as_of: str,
        *,
        limit: int | None = None,
        type: str | list[str] | None = None,
        tags: str | list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """What the agent believed at *as_of* (ISO date or datetime)."""
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.recall_as_of,
                as_of,
                limit=limit,
                type=_as_list(type),
                tags=_as_list(tags),
            )

    def recall_changed_since(
        self,
        since: str,
        *,
        limit: int | None = None,
        type: str | list[str] | None = None,
        tags: str | list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Memories created or updated after *since* (ISO date or datetime)."""
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.recall_changed_since,
                since,
                limit=limit,
                type=_as_list(type),
                tags=_as_list(tags),
            )

    def recall_recent(
        self,
        *,
        limit: int | None = None,
        type: str | list[str] | None = None,
        tags: str | list[str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Most recently created memories, newest first."""
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.recall_recent,
                limit=limit,
                type=_as_list(type),
                tags=_as_list(tags),
            )

    def answer(
        self,
        question: str,
        *,
        limit: int | None = None,
        threshold: float | None = None,
        temperature: float | None = None,
        ai_model: str | None = None,
        kiosk_mode: bool | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Answer *question* grounded in this agent's memories.

        Returns a dict with ``answer`` and the supporting memories.
        """
        with calling_tool(tool_from_source(source)):
            return self._call(
                self.client.answer,
                question,
                limit=limit,
                threshold=threshold,
                temperature=temperature,
                ai_model=ai_model,
                kiosk_mode=kiosk_mode,
            )

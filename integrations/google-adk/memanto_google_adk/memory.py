"""Memanto long-term memory for Google ADK agents.

``MemantoMemoryService`` implements ADK's ``BaseMemoryService``, so ADK's own
``load_memory`` and ``preload_memory`` tools read from Memanto unchanged.

One Memanto agent backs one ADK app (``adk-<app_name>`` unless you pass
``agent_id``). Every memory is tagged with its ADK user, ``user-<sha256>``, and
the service - never the model - decides which user's memories a call can see.
Results are checked against that tag on our side before they are returned.

Conversations are not stored verbatim: new events are run through Memanto's
LLM extraction, which keeps typed, durable memories (preferences, facts,
decisions, commitments...) and drops small talk. ADK may add the same session
many times during its life, so each stored memory carries a marker for the
last event it covered; later calls only extract events after that marker, and
a retry of the same events stores nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlparse

from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
)
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    SessionError,
)
from memanto.cli.client.sdk_client import SdkClient

if TYPE_CHECKING:
    from google.adk.events.event import Event
    from google.adk.sessions.session import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")

SOURCE = "google-adk"
USER_TAG_PREFIX = "user-"
SESSION_TAG_PREFIX = "session-"
# Marks the last event a stored batch covered, so it is never extracted twice.
RETAINED_TAG_PREFIX = "retained-"
API_KEY_ENV = "MOORCHEH_API_KEY"

_TITLE_MAX = 100
_MAX_RECALL = 100  # InputLimits.MAX_K
_MAX_BATCH = 100  # batch_remember's limit
_MAX_EXTRACT = ConversationMemoryExtractionService.MAX_MEMORIES
# Newest rows read back to find a session's retained markers. Rows from one
# batch share a marker, so a handful covers the latest batch.
_MARKER_LOOKBACK = 20


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def user_tag(user_id: str) -> str:
    """The tag that scopes memories to one ADK user."""
    return f"{USER_TAG_PREFIX}{_digest(user_id)}"


def default_agent_id(app_name: str) -> str:
    """The Memanto agent used for *app_name* when no ``agent_id`` is given.

    Memanto agent IDs allow only letters, digits, ``-`` and ``_``.
    """
    return "adk-" + (re.sub(r"[^A-Za-z0-9_-]", "-", app_name).strip("-") or "app")


class _Agent:
    """One Memanto agent with its own client: an SdkClient holds one session."""

    def __init__(self, client: SdkClient, agent_id: str) -> None:
        self.client = client
        self.agent_id = agent_id
        self._ready = False
        self._lock = threading.Lock()

    def _ensure_ready(self) -> None:
        with self._lock:
            if self._ready:
                return
            try:
                self.client.get_agent(self.agent_id)
            except AgentNotFoundError:
                try:
                    self.client.create_agent(
                        agent_id=self.agent_id,
                        description="Google ADK long-term memory (memanto-google-adk)",
                    )
                except AgentAlreadyExistsError:
                    # Another process created it between our check and this call.
                    pass
            self.client.activate_agent(self.agent_id)
            self._ready = True

    def run(self, operation: Callable[[SdkClient], T]) -> T:
        """Run a blocking SDK call, re-activating once if the session died."""
        self._ensure_ready()
        try:
            return operation(self.client)
        except SessionError as exc:
            logger.info("Memanto session invalid (%s); re-activating", exc)
            with self._lock:
                self._ready = False
            self._ensure_ready()
            return operation(self.client)


class MemantoMemoryService(BaseMemoryService):
    """ADK memory service backed by Memanto.

    Args:
        api_key: Moorcheh API key. Defaults to ``$MOORCHEH_API_KEY``.
        agent_id: Memanto agent to use for every app. By default each ADK app
            gets its own agent, ``adk-<app_name>``.
        recall_limit: Maximum memories ``search_memory`` returns.
        extract_max_memories: Maximum memories extracted per stored batch.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        agent_id: str | None = None,
        recall_limit: int = 10,
        extract_max_memories: int = 20,
    ) -> None:
        api_key = api_key or os.environ.get(API_KEY_ENV, "")
        if not api_key.strip():
            raise ValueError(f"api_key is required (or set ${API_KEY_ENV})")
        if not 1 <= recall_limit <= _MAX_RECALL:
            raise ValueError(f"recall_limit must be between 1 and {_MAX_RECALL}")
        if not 1 <= extract_max_memories <= _MAX_EXTRACT:
            raise ValueError(
                f"extract_max_memories must be between 1 and {_MAX_EXTRACT}"
            )
        self._api_key = api_key
        self._agent_id = agent_id
        self._recall_limit = recall_limit
        self._extract_max_memories = extract_max_memories
        self._agents: dict[str, _Agent] = {}
        self._agents_lock = threading.Lock()

    @classmethod
    def from_uri(cls, uri: str, **_: Any) -> MemantoMemoryService:
        """Factory for ADK's service registry: ``memanto://`` or ``memanto://<agent_id>``.

        ADK passes extra keyword arguments such as ``agents_dir``; they are ignored.
        """
        return cls(agent_id=urlparse(uri).netloc or None)

    # ------------------------------------------------------------------ #
    # BaseMemoryService
    # ------------------------------------------------------------------ #

    async def add_session_to_memory(self, session: Session) -> None:
        """Extract and store what is new in *session* since the last call."""
        await asyncio.to_thread(self._add_session, session)

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Extract and store *events*, a delta such as the latest turn."""
        await asyncio.to_thread(
            self._add_events, app_name, user_id, list(events), session_id
        )

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Store explicit memories as-is, without extraction.

        Each entry's ``custom_metadata["type"]`` picks the Memanto memory type
        (default ``fact``).
        """
        await asyncio.to_thread(self._add_memory, app_name, user_id, list(memories))

    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Semantic recall over this user's memories in this app."""
        return await asyncio.to_thread(self._search, app_name, user_id, query)

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def _add_session(self, session: Session) -> None:
        agent = self._agent(session.app_name)
        tag = user_tag(session.user_id)
        session_tag = self._session_tag(tag, session.id)
        retained = self._markers(agent, session_tag)
        events = list(session.events)
        # Resume after the newest event a previous call already stored.
        for index in range(len(events) - 1, -1, -1):
            if self._marker(tag, events[index].id) in retained:
                events = events[index + 1 :]
                break
        self._retain(agent, tag, session_tag, events)

    def _add_events(
        self,
        app_name: str,
        user_id: str,
        events: list[Event],
        session_id: str | None,
    ) -> None:
        messages = _messages(events)
        if not messages:
            return
        agent = self._agent(app_name)
        tag = user_tag(user_id)
        last_event_id = messages[-1][0]
        marker = self._marker(tag, last_event_id)
        if marker in self._markers(agent, marker):
            logger.info("Events up to %s were already stored; skipping", last_event_id)
            return
        session_tag = self._session_tag(tag, session_id) if session_id else None
        self._retain(agent, tag, session_tag, events)

    def _retain(
        self,
        agent: _Agent,
        tag: str,
        session_tag: str | None,
        events: list[Event],
    ) -> None:
        """Extract and store *events* in chunks the extractor accepts whole.

        The extractor silently drops text past its character budget, so a long
        backlog is split rather than truncated. Each chunk is stored with the
        marker of its own last event, so a failure part-way through resumes
        from the last chunk that was stored.
        """
        extractor = ConversationMemoryExtractionService(agent.client._get_moorcheh())
        for chunk in _chunks(_messages(events)):
            conversation = [message for _, message in chunk]
            if not any(m["role"] == "user" for m in conversation):
                continue
            try:
                candidates = extractor.extract(
                    namespace="",  # extraction runs the raw LLM; no namespace is read
                    messages=conversation,
                    max_memories=self._extract_max_memories,
                )
            except ValueError as exc:
                # Raised both when the turn held nothing worth keeping and when
                # the LLM output was unusable; the two are indistinguishable here.
                logger.info("Memory extraction returned nothing: %s", exc)
                continue
            tags = [tag, SOURCE, self._marker(tag, chunk[-1][0])]
            if session_tag:
                tags.insert(1, session_tag)
            self._store(
                agent, [{**c, "tags": tags, "source": SOURCE} for c in candidates]
            )

    def _store(self, agent: _Agent, items: list[dict[str, Any]]) -> None:
        """batch_remember in slices of its 100-item limit; log rejected items."""
        for start in range(0, len(items), _MAX_BATCH):
            batch = items[start : start + _MAX_BATCH]

            def remember(client: SdkClient, batch: list[dict[str, Any]] = batch) -> Any:
                return client.batch_remember(agent_id=agent.agent_id, memories=batch)

            result = agent.run(remember)
            # batch_remember reports per-item rejections instead of raising.
            for row in result.get("results") or []:
                if row.get("status") == "failed":
                    logger.warning(
                        "Memanto rejected a memory: %s",
                        row.get("error") or row.get("reason"),
                    )

    def _add_memory(
        self, app_name: str, user_id: str, memories: list[MemoryEntry]
    ) -> None:
        tag = user_tag(user_id)
        items = []
        for entry in memories:
            text = _text(entry.content)
            if not text:
                continue
            memory_type = str(entry.custom_metadata.get("type") or "fact").lower()
            if memory_type not in VALID_MEMORY_TYPES:
                raise ValueError(
                    f"Invalid memory type '{memory_type}'. Use one of: "
                    + ", ".join(sorted(VALID_MEMORY_TYPES))
                )
            items.append(
                {
                    "type": memory_type,
                    "title": _truncate(text.splitlines()[0], _TITLE_MAX),
                    "content": text,
                    "tags": [tag, SOURCE],
                    "source": SOURCE,
                    "provenance": "explicit_statement",
                }
            )
        if items:
            self._store(self._agent(app_name), items)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def _search(self, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        if not query.strip():
            return SearchMemoryResponse()
        agent = self._agent(app_name)
        tag = user_tag(user_id)
        result = agent.run(
            lambda client: client.recall(
                agent_id=agent.agent_id,
                query=query,
                limit=self._recall_limit,
                tags=[tag],
                status="active",
            )
        )
        # The backend tag filter is not trusted alone: a miss would surface
        # another user's memory.
        rows = [m for m in result.get("memories") or [] if tag in (m.get("tags") or [])]
        return SearchMemoryResponse(memories=[_entry(m) for m in rows])

    def _markers(self, agent: _Agent, scope_tag: str) -> set[str]:
        """Retained markers on the newest rows carrying *scope_tag*."""
        result = agent.run(
            lambda client: client.recall_recent(
                agent_id=agent.agent_id,
                limit=_MARKER_LOOKBACK,
                tags=[scope_tag],
                status="all",
            )
        )
        return {
            str(t)
            for m in result.get("memories") or []
            if scope_tag in (m.get("tags") or [])
            for t in m.get("tags") or []
            if str(t).startswith(RETAINED_TAG_PREFIX)
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _agent(self, app_name: str) -> _Agent:
        agent_id = self._agent_id or default_agent_id(app_name)
        with self._agents_lock:
            if agent_id not in self._agents:
                self._agents[agent_id] = _Agent(SdkClient(self._api_key), agent_id)
            return self._agents[agent_id]

    @staticmethod
    def _session_tag(user: str, session_id: str) -> str:
        return f"{SESSION_TAG_PREFIX}{_digest(user, session_id)}"

    @staticmethod
    def _marker(user: str, event_id: str) -> str:
        return f"{RETAINED_TAG_PREFIX}{_digest(user, event_id)}"


def _text(content: types.Content | None) -> str:
    if not content or not content.parts:
        return ""
    return "\n".join(p.text for p in content.parts if p.text and not p.thought).strip()


def _messages(events: list[Event]) -> list[tuple[str, dict[str, str]]]:
    """(event id, message) for user and agent text; tool calls are skipped."""
    messages = []
    for event in events:
        text = _text(event.content)
        if event.partial or not text:
            continue
        role = "user" if event.author == "user" else "assistant"
        messages.append((event.id, {"role": role, "content": text}))
    return messages


def _chunks(
    messages: list[tuple[str, dict[str, str]]],
) -> list[list[tuple[str, dict[str, str]]]]:
    """Split *messages* to fit the extractor's message and character limits."""
    limits = ConversationMemoryExtractionService
    chunks: list[list[tuple[str, dict[str, str]]]] = []
    current: list[tuple[str, dict[str, str]]] = []
    size = 0
    for item in messages:
        # The extractor renders each message as "role: content" plus a newline.
        length = len(item[1]["role"]) + len(item[1]["content"]) + 3
        if current and (
            len(current) >= limits.MAX_MESSAGES
            or size + length > limits.MAX_CONTENT_CHARS
        ):
            chunks.append(current)
            current, size = [], 0
        current.append(item)
        size += length
    if current:
        chunks.append(current)
    return chunks


def _entry(memory: dict[str, Any]) -> MemoryEntry:
    title = memory.get("title") or ""
    content = memory.get("content") or ""
    text = (
        f"[{memory.get('type') or 'memory'}] {title}: {content}" if title else content
    )
    return MemoryEntry(
        id=memory.get("id"),
        content=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
        timestamp=memory.get("created_at"),
        custom_metadata={
            key: memory[key]
            for key in ("type", "title", "confidence", "provenance", "tags", "score")
            if memory.get(key) is not None
        },
    )


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."

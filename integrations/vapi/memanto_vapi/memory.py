"""Memanto memory for Vapi voice agents.

One Memanto agent backs one Vapi assistant. Its memory is **shared** by every
call: organization knowledge you load into the agent, plus the lessons the
voice agent learns from its own calls (mistakes, corrections, better answers).

With ``scope="caller"`` each caller additionally gets private memories, stored
under a ``caller-<hmac>`` tag derived from their phone number (or
``customer.externalId`` for web/chat). Raw phone numbers are never stored, and
the server - not the model - decides whose private memories a call can read.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Literal, TypeVar

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

logger = logging.getLogger(__name__)

T = TypeVar("T")
Scope = Literal["shared", "caller"]
SCOPES: tuple[Scope, ...] = ("shared", "caller")

RECALL_TOOL = "memanto_recall"
REMEMBER_TOOL = "memanto_remember"
CONTEXT_VARIABLE = "memanto_context"
CALLER_TAG_PREFIX = "caller-"
# Marks what end-of-call learning stored, so a webhook retry is not learned twice.
RETAINED_TAG_PREFIX = "retained-"
SOURCE = "vapi"

# At call start nobody has spoken yet, so the semantic half of recall uses a
# fixed query aimed at what a voice agent needs up front.
SHARED_START_QUERY = (
    "lessons learned, mistakes to avoid, policies, instructions and key facts"
)
CALLER_START_QUERY = "caller profile, preferences, open issues and commitments"
NO_MEMORY_CONTEXT = "No saved memories yet."

_TITLE_MAX = 100
_MAX_RECALL = 100  # InputLimits.MAX_K
# ConversationMemoryExtractionService rejects more than 200 messages.
_MAX_EXTRACT_MESSAGES = 200

_NO_SECRETS = (
    "Never include secrets, passwords, payment card numbers, or other "
    "sensitive credentials."
)
SHARED_EXTRACTION_FOCUS = (
    "Extract lessons this voice agent should apply on future calls with ANY "
    "caller: mistakes the agent made and how to avoid them, corrections it "
    "received, answers or approaches that worked better, and facts about the "
    "business, its products, or its policies that came up. Never include "
    "anything about the specific caller: no names, contact details, account "
    "data, personal preferences, or promises made to them. "
    "Prefer the types learning, error, instruction, decision and fact. " + _NO_SECRETS
)
CALLER_EXTRACTION_FOCUS = (
    "Extract durable details about this specific caller that would help on "
    "their next call: who they are, their preferences, open issues, and "
    "commitments made to them. Do not include general lessons for the agent. "
    + _NO_SECRETS
)


def caller_identity(message: dict[str, Any]) -> str | None:
    """Return a stable caller identity from a Vapi server message, or None.

    Vapi sends ``customer`` both at the top level of the message and on
    ``call``. The phone number wins; ``externalId`` covers web and chat calls
    that have no number. The key is kept in the identity so a number and an
    external id with the same text never collide.
    """
    call = message.get("call") or {}
    customer = message.get("customer") or call.get("customer") or {}
    for key in ("number", "externalId"):
        value = customer.get(key)
        if isinstance(value, str) and value.strip():
            return f"{key}:{value.strip()}"
    return None


class _FocusedExtraction(ConversationMemoryExtractionService):
    """The standard extractor with its instructions replaced by *focus*."""

    def __init__(self, client: Any, focus: str) -> None:
        super().__init__(client)
        self._focus = focus

    def _header_prompt(self, max_memories: int) -> str:
        return (
            f"{self._focus} Only include memories useful in future calls. "
            f"Keep each memory content at or below {self.MAX_MEMORY_CONTENT_CHARS} "
            f"characters. Return at most {max_memories} memories. "
            f"Valid types: {', '.join(sorted(VALID_MEMORY_TYPES))}."
        )


class VapiMemory:
    """Recall at call start, memory tools during the call, learning after it."""

    def __init__(
        self,
        client: SdkClient,
        *,
        agent_id: str,
        scope: Scope = "shared",
        caller_salt: str | None = None,
        recall_limit: int = 10,
        recall_timeout: float = 3.0,
        max_context_chars: int = 4000,
        extract_max_memories: int = 20,
    ) -> None:
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
        if scope == "caller" and not caller_salt:
            raise ValueError(
                "caller_salt is required for scope='caller': phone numbers are "
                "guessable, so an unsalted hash would not protect them"
            )
        self._client = client
        self.agent_id = agent_id
        self.scope: Scope = scope
        self._salt = (caller_salt or "").encode("utf-8")
        self._recall_limit = recall_limit
        self._recall_timeout = recall_timeout
        self._max_context_chars = max_context_chars
        self._extract_max_memories = extract_max_memories
        self._ready = False
        self._ready_lock = threading.Lock()
        self._retention_locks_guard = threading.Lock()
        self._retention_locks: dict[str, tuple[threading.Lock, int]] = {}

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #

    def caller_tag(self, identity: str) -> str:
        """Map a caller identity to its private tag (``caller-`` + 32 hex chars)."""
        digest = hmac.new(self._salt, identity.encode("utf-8"), hashlib.sha256)
        return f"{CALLER_TAG_PREFIX}{digest.hexdigest()[:32]}"

    def _caller_tag_for(self, message: dict[str, Any]) -> str | None:
        """The caller's private tag, or None in shared scope or for unknown callers."""
        if self.scope != "caller":
            return None
        identity = caller_identity(message)
        return self.caller_tag(identity) if identity else None

    # ------------------------------------------------------------------ #
    # Session handling
    # ------------------------------------------------------------------ #

    def ensure_ready(self) -> None:
        """Create the Memanto agent if missing and activate its session once."""
        with self._ready_lock:
            if self._ready:
                return
            try:
                self._client.get_agent(self.agent_id)
            except AgentNotFoundError:
                try:
                    self._client.create_agent(
                        agent_id=self.agent_id,
                        pattern="support",
                        description="Vapi voice agent memory (memanto-vapi)",
                    )
                except AgentAlreadyExistsError:
                    # Another instance created it between our check and this
                    # call; that is the outcome we wanted anyway.
                    pass
            self._client.activate_agent(self.agent_id)
            self._ready = True

    def _run(self, operation: Callable[[], T]) -> T:
        """Run a blocking SDK operation, re-activating once if the session died."""
        self.ensure_ready()
        try:
            return operation()
        except SessionError as exc:
            logger.info("Memanto session invalid (%s); re-activating", exc)
            with self._ready_lock:
                self._ready = False
            self.ensure_ready()
            return operation()

    # ------------------------------------------------------------------ #
    # Call start: assistant-request / outbound call creation
    # ------------------------------------------------------------------ #

    async def build_assistant_overrides(
        self, message: dict[str, Any]
    ) -> dict[str, Any]:
        """Return ``assistantOverrides`` carrying ``{{memanto_context}}``.

        *message* is a Vapi server message, or for calls you create yourself
        any dict with a ``customer`` key, e.g.
        ``{"customer": {"number": "+15551234567"}}`` (or ``{}`` in shared scope).

        Fails open: if recall errors or exceeds ``recall_timeout`` (Vapi gives
        ``assistant-request`` 7.5s end to end), the context is empty and the
        call proceeds without memory.
        """
        return {"variableValues": {CONTEXT_VARIABLE: await self.call_context(message)}}

    async def call_context(self, message: dict[str, Any]) -> str:
        """Text for ``{{memanto_context}}`` at the start of a call."""
        tag = self._caller_tag_for(message)
        try:
            shared, private = await asyncio.wait_for(
                self._load_call_start(tag), timeout=self._recall_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Memanto recall exceeded %.1fs; starting call without memory",
                self._recall_timeout,
            )
            return ""
        except Exception:
            logger.exception("Memanto recall failed; starting call without memory")
            return ""
        return self._format_sections(shared, private) or NO_MEMORY_CONTEXT

    async def _load_call_start(
        self, tag: str | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        await asyncio.to_thread(self.ensure_ready)
        lookups = [
            asyncio.to_thread(self._recent, None),
            asyncio.to_thread(self._search, None, SHARED_START_QUERY),
        ]
        if tag:
            lookups += [
                asyncio.to_thread(self._recent, tag),
                asyncio.to_thread(self._search, tag, CALLER_START_QUERY),
            ]
        found = await asyncio.gather(*lookups)
        shared = _merge(found[0] + found[1])
        private = _merge(found[2] + found[3]) if tag else []
        return shared, private

    # ------------------------------------------------------------------ #
    # During the call: tool-calls
    # ------------------------------------------------------------------ #

    async def handle_tool_calls(self, message: dict[str, Any]) -> dict[str, Any]:
        """Answer a Vapi ``tool-calls`` message for the memanto_* tools."""
        tag = self._caller_tag_for(message)
        call_id = (message.get("call") or {}).get("id")
        results = []
        for tool_call in message.get("toolCallList") or []:
            function = tool_call.get("function") or {}
            name = function.get("name") or tool_call.get("name") or ""
            entry: dict[str, Any] = {"name": name, "toolCallId": tool_call.get("id")}
            try:
                arguments = function.get("arguments", tool_call.get("arguments"))
                if isinstance(arguments, str):
                    arguments = json.loads(arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments must be a JSON object")
                if name == RECALL_TOOL:
                    entry["result"] = await asyncio.to_thread(
                        self._tool_recall, tag, arguments
                    )
                elif name == REMEMBER_TOOL:
                    entry["result"] = await asyncio.to_thread(
                        self._tool_remember, tag, call_id, arguments
                    )
                else:
                    raise ValueError(f"Unknown tool '{name}'")
            except ValueError as exc:
                entry["error"] = str(exc)
            except Exception:
                logger.exception("Memanto tool '%s' failed", name)
                entry["error"] = "Memory service error; continue without it."
            results.append(entry)
        return {"results": results}

    def _tool_recall(self, tag: str | None, arguments: dict[str, Any]) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("'query' is required")
        shared = self._search(None, query)
        private = self._search(tag, query) if tag else []
        return self._format_sections(shared, private) or "No matching memories."

    def _tool_remember(
        self, tag: str | None, call_id: str | None, arguments: dict[str, Any]
    ) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("'content' is required")
        memory_type = str(arguments.get("type") or "fact").strip().lower()
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid type '{memory_type}'. Use one of: "
                + ", ".join(sorted(VALID_MEMORY_TYPES))
            )
        # In caller scope everything the model saves mid-call is private to the
        # caller it is talking to. Letting the model mark its own write as
        # "shared" would let a caller talk their details into every other
        # caller's context; shared lessons come from end-of-call extraction,
        # whose prompt forbids caller details.
        private_tag = None
        if self.scope == "caller":
            if tag is None:
                raise ValueError(
                    "Cannot save a memory: the caller could not be identified"
                )
            private_tag = tag
        title = str(arguments.get("title") or "").strip() or content
        self._run(
            lambda: self._client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=_truncate(title, _TITLE_MAX),
                content=content,
                tags=_tags(private_tag, call_id),
                source=SOURCE,
                provenance="explicit_statement",
            )
        )
        return "Saved."

    # ------------------------------------------------------------------ #
    # After the call: end-of-call-report
    # ------------------------------------------------------------------ #

    async def retain_call(self, message: dict[str, Any]) -> None:
        """Learn from an ``end-of-call-report`` and store the results."""
        await asyncio.to_thread(self._retain_call, message)

    def _retain_call(self, message: dict[str, Any]) -> None:
        """Retain extracted details; keep Vapi's raw call summary caller-private."""
        call_id = (message.get("call") or {}).get("id")
        with self._retention_lock(call_id):
            self._retain_call_once(message, call_id)

    @contextmanager
    def _retention_lock(self, call_id: str | None) -> Iterator[None]:
        """Serialize overlapping deliveries for one call without leaking locks."""
        if not call_id:
            yield
            return

        with self._retention_locks_guard:
            lock, users = self._retention_locks.get(call_id, (threading.Lock(), 0))
            self._retention_locks[call_id] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._retention_locks_guard:
                current_lock, users = self._retention_locks[call_id]
                if users == 1:
                    del self._retention_locks[call_id]
                else:
                    self._retention_locks[call_id] = (current_lock, users - 1)

    def _retain_call_once(self, message: dict[str, Any], call_id: str | None) -> None:
        """Retain one report while its call-specific critical section is held."""
        if call_id and self._already_retained(call_id):
            logger.info("Call %s was already retained; skipping retry", call_id)
            return

        artifact = message.get("artifact") or {}
        conversation = [
            {"role": m["role"], "content": m["content"].strip()}
            for m in artifact.get("messagesOpenAIFormatted") or []
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
            and m["content"].strip()
        ][-(_MAX_EXTRACT_MESSAGES - 1) :]  # one slot is kept for the notes below
        if not any(m["role"] == "user" for m in conversation):
            logger.info("Call %s has no caller speech; nothing to learn", call_id)
            return

        analysis = message.get("analysis") or {}
        summary = str(analysis.get("summary") or "").strip()
        evaluation = str(analysis.get("successEvaluation") or "").strip()
        # Vapi's own verdict on the call helps the extractor spot mistakes.
        notes = [
            f"Vapi call summary: {summary}" if summary else "",
            f"Vapi success evaluation: {evaluation}" if evaluation else "",
        ]
        if any(notes):
            conversation.append(
                {"role": "system", "content": "\n".join(n for n in notes if n)}
            )

        tag = self._caller_tag_for(message)
        if self.scope == "caller":
            # Caller speech is untrusted input. Never promote memories inferred
            # from one caller's transcript into the shared namespace: prompt
            # instructions are not an authorization boundary. Fail closed when
            # the caller cannot be identified, otherwise keep every automatic
            # end-of-call memory private to that caller.
            if tag is None:
                logger.info(
                    "Call %s has no caller identity; automatic retention skipped",
                    call_id,
                )
                return
            items = self._extract(conversation, CALLER_EXTRACTION_FOCUS, tag, call_id)
        else:
            items = self._extract(conversation, SHARED_EXTRACTION_FOCUS, None, call_id)

        # Vapi's raw summary is written from the caller's transcript and can
        # name the caller or repeat their details. It never passes the shared
        # extraction focus, so, as on main, it is kept only as caller-private
        # memory; shared scope keeps only the filtered lessons above.
        if tag and summary:
            items.append(
                {
                    "type": "event",
                    "title": f"Call summary {str(message.get('endedAt') or '')[:10]}".strip(),
                    "content": summary,
                    "confidence": 0.8,
                    "tags": _retention_tags(tag, call_id),
                    "source": SOURCE,
                    "provenance": "inferred",
                }
            )

        if not items:
            logger.info("Call %s produced no memories", call_id)
            return
        result = self._run(
            lambda: self._client.batch_remember(agent_id=self.agent_id, memories=items)
        )
        logger.info(
            "Retained call %s: %s of %s memories stored",
            call_id,
            result.get("successful"),
            len(items),
        )

    def _extract(
        self,
        conversation: list[dict[str, str]],
        focus: str,
        tag: str | None,
        call_id: str | None,
    ) -> list[dict[str, Any]]:
        extractor = _FocusedExtraction(self._client._get_moorcheh(), focus)
        try:
            candidates = extractor.extract(
                namespace="",  # extraction runs the raw LLM; no namespace is read
                messages=conversation,
                max_memories=self._extract_max_memories,
            )
        except ValueError as exc:
            # Raised both when the call held nothing worth keeping and when the
            # LLM output was unusable; the two are indistinguishable here.
            logger.info("Extraction for call %s returned nothing: %s", call_id, exc)
            return []
        return [
            {**candidate, "tags": _retention_tags(tag, call_id), "source": SOURCE}
            for candidate in candidates
        ]

    def _already_retained(self, call_id: str) -> bool:
        """True when this call's end-of-call report was already learned from.

        Vapi retries a webhook it believes failed, and the report carries the
        whole conversation, so a retry would extract and store everything a
        second time.
        """
        marker = f"{RETAINED_TAG_PREFIX}{call_id}"
        try:
            result = self._run(
                lambda: self._client.recall(
                    agent_id=self.agent_id,
                    query=marker,
                    limit=1,
                    tags=[marker],
                    status="all",
                )
            )
        except Exception:
            logger.exception(
                "Retention check failed for call %s; retaining anyway", call_id
            )
            return False
        # Trust the marker only when a returned row really carries it.
        return any(
            marker in (m.get("tags") or []) for m in result.get("memories") or []
        )

    # ------------------------------------------------------------------ #
    # Recall helpers
    # ------------------------------------------------------------------ #

    def _fetch_limit(self) -> int:
        # In caller scope, shared lookups also return other callers' private
        # rows, which are dropped afterwards; over-fetch so enough survive.
        if self.scope == "caller":
            return min(self._recall_limit * 3, _MAX_RECALL)
        return self._recall_limit

    def _search(self, tag: str | None, query: str) -> list[dict[str, Any]]:
        result = self._run(
            lambda: self._client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=self._recall_limit if tag else self._fetch_limit(),
                tags=[tag] if tag else None,
                status="active",
            )
        )
        return self._visible(result.get("memories") or [], tag)

    def _recent(self, tag: str | None) -> list[dict[str, Any]]:
        result = self._run(
            lambda: self._client.recall_recent(
                agent_id=self.agent_id,
                limit=self._recall_limit if tag else self._fetch_limit(),
                tags=[tag] if tag else None,
                status="active",
            )
        )
        return self._visible(result.get("memories") or [], tag)

    def _visible(
        self, memories: list[dict[str, Any]], tag: str | None
    ) -> list[dict[str, Any]]:
        """Keep only rows this lookup may show, checked exactly on our side.

        Shared lookups drop every caller-private row; private lookups keep only
        this caller's rows. The backend tag filter is not trusted alone, because
        a miss would surface another caller's memory.
        """
        if tag:
            visible = [m for m in memories if tag in (m.get("tags") or [])]
        else:
            visible = [
                m
                for m in memories
                if not any(
                    str(t).startswith(CALLER_TAG_PREFIX) for t in m.get("tags") or []
                )
            ]
        return visible[: self._recall_limit]

    def _format_sections(
        self, shared: list[dict[str, Any]], private: list[dict[str, Any]]
    ) -> str:
        budget = self._max_context_chars
        sections = []
        for heading, memories in (
            ("Knowledge and lessons learned:", shared),
            ("About this caller:", private),
        ):
            lines = []
            for memory in memories:
                date = str(memory.get("created_at") or "")[:10]
                line = (
                    f"- [{memory.get('type') or 'memory'}] "
                    f"{memory.get('title') or ''}: {memory.get('content') or ''}"
                    + (f" ({date})" if date else "")
                )
                if len(line) + 1 > budget:
                    break
                lines.append(line)
                budget -= len(line) + 1
            if lines:
                sections.append(heading + "\n" + "\n".join(lines))
        return "\n\n".join(sections)


def _merge(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-duplicate by id, newest first.

    A row without an id cannot be matched against anything, so it is kept
    rather than folded into every other id-less row.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for position, memory in enumerate(memories):
        key = str(memory.get("id") or f"__no-id-{position}")
        by_id.setdefault(key, memory)
    return sorted(
        by_id.values(), key=lambda m: str(m.get("created_at") or ""), reverse=True
    )


def _tags(caller_tag: str | None, call_id: str | None) -> list[str]:
    tags = [SOURCE]
    if caller_tag:
        tags.insert(0, caller_tag)
    if call_id:
        tags.append(f"call-{call_id}")
    return tags


def _retention_tags(caller_tag: str | None, call_id: str | None) -> list[str]:
    """Tags for end-of-call memories, including the retry marker."""
    tags = _tags(caller_tag, call_id)
    if call_id:
        tags.append(f"{RETAINED_TAG_PREFIX}{call_id}")
    return tags


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."

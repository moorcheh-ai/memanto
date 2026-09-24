"""Runtime adapter: recall before each turn, retain after (AgentCore-compatible pattern)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from memanto.app.utils.errors import SessionError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

_MAX_AGENT_ID_LENGTH = 64
_READABLE_COMPONENT_RE = re.compile(r"[A-Za-z0-9_-]+")
_STRUCTURED_SEPARATOR = "\x1f"


class AgentResolutionError(ValueError):
    """Raised when stable user identity is missing (fail closed)."""


@dataclass(frozen=True)
class TurnContext:
    """One AgentCore Runtime invocation."""

    runtime_session_id: str
    user_id: str
    agent_name: str
    tenant_id: str | None = None
    request_id: str | None = None


def _occurrences(haystack: str, needle: str) -> int:
    """Count occurrences of *needle* in *haystack*, overlapping ones included."""
    return len(re.findall(f"(?={re.escape(needle)})", haystack))


def default_agent_id_resolver(context: TurnContext) -> str:
    """Map tenant + user + agent to a Memanto agent_id (not runtimeSessionId).

    Every distinct (tenant, user, agent) triple must land in its own Memanto
    namespace, so this mapping has to be injective. Memanto agent IDs allow
    only ``[A-Za-z0-9_-]``; the readable form
    ``tenant-{tenant}-user-{user}-agent-{agent}`` is used only when it can be
    parsed back unambiguously: every component is already within that charset
    (nothing is rewritten) and the ``-user-`` / ``-agent-`` delimiters each
    occur exactly once. Anything else (emails, dotted usernames, non-Latin
    names, components containing a delimiter, or long keys) is hashed from the
    structured components instead, so it can never fold into another user.
    """
    if not (context.user_id or "").strip():
        raise AgentResolutionError(
            "user_id is required for cross-session memory; do not use runtimeSessionId"
        )
    if not (context.agent_name or "").strip():
        raise AgentResolutionError("agent_name is required")

    tenant = context.tenant_id or "default"
    user = context.user_id
    agent = context.agent_name
    components = (tenant, user, agent)
    if any(_STRUCTURED_SEPARATOR in part for part in components):
        raise AgentResolutionError(
            "tenant_id, user_id and agent_name must not contain control character U+001F"
        )

    readable = f"tenant-{tenant}-user-{user}-agent-{agent}"
    if (
        len(readable) <= _MAX_AGENT_ID_LENGTH
        and all(_READABLE_COMPONENT_RE.fullmatch(part) for part in components)
        and _occurrences(readable, "-user-") == 1
        and _occurrences(readable, "-agent-") == 1
    ):
        return readable
    structured = _STRUCTURED_SEPARATOR.join(components)
    digest = hashlib.sha256(structured.encode("utf-8")).hexdigest()
    return digest[:_MAX_AGENT_ID_LENGTH]


def _format_recall(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["Relevant memories:"]
    for i, mem in enumerate(memories, 1):
        title = mem.get("title", "Untitled")
        content = mem.get("content", "")
        mem_type = mem.get("type", "unknown")
        lines.append(f"{i}. [{mem_type}] {title}: {content}")
    return "\n".join(lines)


def _truncate_title(text: str, max_len: int = 100) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text or "AgentCore turn"
    return text[: max_len - 3] + "..."


class MemantoRuntimeAdapter:
    """Recall → execute → retain cycle for ephemeral AgentCore Runtime sessions."""

    def __init__(
        self,
        client: SdkClient,
        *,
        agent_name: str | None = None,
        agent_id_resolver: Callable[[TurnContext], str] | None = None,
        recall_limit: int = 10,
        retain_async: bool = True,
        retain_memory_type: str = "event",
        retain_source: str = "agentcore-runtime",
    ) -> None:
        self._client = client
        self._default_agent_name = agent_name
        self._agent_id_resolver = agent_id_resolver or default_agent_id_resolver
        self._recall_limit = recall_limit
        self._retain_async = retain_async
        self._retain_memory_type = retain_memory_type
        self._retain_source = retain_source
        self._setup_lock = asyncio.Lock()
        self._session_ready: set[str] = set()

    def resolve_agent_id(self, context: TurnContext) -> str:
        if not (context.user_id or "").strip():
            raise AgentResolutionError(
                "user_id is required for cross-session memory; do not use runtimeSessionId"
            )
        if context.agent_name:
            return self._agent_id_resolver(context)
        if self._default_agent_name:
            return self._agent_id_resolver(
                TurnContext(
                    runtime_session_id=context.runtime_session_id,
                    user_id=context.user_id,
                    agent_name=self._default_agent_name,
                    tenant_id=context.tenant_id,
                    request_id=context.request_id,
                )
            )
        raise AgentResolutionError("agent_name missing and no default configured")

    async def _ensure_session(self, agent_id: str) -> None:
        """Bind the shared SdkClient to *agent_id* (caller must hold ``_setup_lock``)."""
        if agent_id not in self._session_ready:

            def _create() -> None:
                try:
                    self._client.create_agent(agent_id=agent_id, pattern="tool")
                except Exception as exc:
                    logger.debug("create_agent ignored for %s: %s", agent_id, exc)

            await asyncio.to_thread(_create)
            self._session_ready.add(agent_id)

        if self._client.agent_id != agent_id:

            def _activate() -> None:
                try:
                    self._client.activate_agent(agent_id, duration_hours=6)
                except Exception as exc:
                    logger.debug("activate_agent ignored for %s: %s", agent_id, exc)

            await asyncio.to_thread(_activate)

    async def before_turn(self, context: TurnContext, *, query: str) -> str:
        """Recall memories for *query*; returns prompt context or \"\" on failure."""
        try:
            agent_id = self.resolve_agent_id(context)
        except AgentResolutionError:
            raise
        except Exception as exc:
            logger.warning("Agent id resolution failed: %s", exc)
            return ""

        try:
            async with self._setup_lock:
                await self._ensure_session(agent_id)

                def _recall() -> dict[str, Any]:
                    return self._client.recall(
                        agent_id=agent_id,
                        query=query,
                        limit=self._recall_limit,
                    )

                try:
                    result = await asyncio.to_thread(_recall)
                except SessionError:
                    self._session_ready.discard(agent_id)
                    await self._ensure_session(agent_id)
                    result = await asyncio.to_thread(_recall)
        except Exception as exc:
            logger.warning("Memanto recall failed (continuing without memory): %s", exc)
            return ""

        return _format_recall(result.get("memories") or [])

    async def after_turn(
        self,
        context: TurnContext,
        *,
        result: str,
        query: str,
    ) -> None:
        """Retain turn output; non-blocking when ``retain_async`` is True."""
        coro = self._after_turn_impl(context, result=result, query=query)
        if self._retain_async:
            asyncio.create_task(coro)
            return
        await coro

    async def _after_turn_impl(
        self,
        context: TurnContext,
        *,
        result: str,
        query: str,
    ) -> None:
        try:
            agent_id = self.resolve_agent_id(context)
        except Exception as exc:
            logger.warning("Skipping retain — bad identity: %s", exc)
            return

        content = (
            f"User: {query.strip()}\n\n"
            f"Agent: {result.strip()}\n\n"
            f"(runtime_session={context.runtime_session_id})"
        )
        if len(content) > 10_000:
            content = content[-10_000:]
        title = _truncate_title(query)

        async def _retain_once() -> None:
            async with self._setup_lock:
                await self._ensure_session(agent_id)

                def _remember() -> None:
                    self._client.remember(
                        agent_id=agent_id,
                        memory_type=self._retain_memory_type,
                        title=title,
                        content=content,
                        source=self._retain_source,
                        provenance="observed",
                        tags=["agentcore", "turn"],
                    )

                try:
                    await asyncio.to_thread(_remember)
                except SessionError:
                    self._session_ready.discard(agent_id)
                    await self._ensure_session(agent_id)
                    await asyncio.to_thread(_remember)

        try:
            await _retain_once()
        except Exception as exc:
            logger.warning("Memanto retain failed (turn unaffected): %s", exc)

    async def run_turn(
        self,
        context: TurnContext,
        *,
        payload: dict[str, Any],
        agent_callable: Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Full turn: recall, call agent, retain output."""
        query = str(payload.get("prompt") or payload.get("query") or "")
        memory_context = await self.before_turn(context, query=query)
        agent_result = await agent_callable(payload, memory_context)
        output = agent_result.get("output")
        if output is not None:
            await self.after_turn(context, result=str(output), query=query)
        return agent_result

"""SkillMemory — the single integration point between Claude Code skills and Memanto.

Wraps Memanto's ``SdkClient`` with the three operations the bounty calls for:

* ``recall_for_skill``  — dynamic injection: pull memories relevant to the skill
                          being invoked and render an injectable context block.
* ``distill_and_store`` — active extraction: use the backend LLM to distill a
                          finished session into typed memories, then persist them.
* ``profile_block``     — the accumulated Engineering Profile (for SessionStart).

Agent + session lifecycle is idempotent and lazy: ``setup`` is safe to call on
every hook invocation, mirroring the pattern used by the official MCP and
LangGraph integrations in this repo.
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.app.utils.errors import AgentAlreadyExistsError, AgentNotFoundError
from memanto.cli.client.sdk_client import SdkClient

from . import extractor
from .config import SkillsConfig
from .profile import MemoryProfile
from .skill_map import normalize_skill, route_for

logger = logging.getLogger(__name__)

# Stamped onto every memory this layer writes, so skill memories are filterable
# and separable from memories written by other Memanto integrations.
SOURCE_TAG = "claudecode-skills-memanto"

# Memanto session lifetime requested on activation. Sessions are JWT-backed and
# auto-renewed by the SDK when nearing expiry, so the exact value is not load-bearing.
_SESSION_HOURS = 6


class SkillMemory:
    """Drop-in cross-session memory companion for Claude Code skills."""

    def __init__(
        self,
        config: SkillsConfig | None = None,
        client: SdkClient | None = None,
    ) -> None:
        self.config = config or SkillsConfig.from_env()
        # ``client`` injection keeps this unit-testable without a network.
        self._sdk = client or SdkClient(api_key=self.config.api_key)
        self._ready = False

    # ------------------------------------------------------------------ #
    # Lifecycle (idempotent, lazy)
    # ------------------------------------------------------------------ #

    def setup(self) -> None:
        """Ensure the agent exists and a session is active. Safe to repeat.

        Activation is attempted first: each hook runs in a fresh process, and
        for the common case (the agent already exists) this costs one network
        call instead of two. Creation only happens on AgentNotFoundError.

        Exceptions propagate to the caller. Hook entry points are wrapped in
        ``_common.run()``, which catches all exceptions and exits 0, so a
        failed setup never blocks Claude Code. Demo scripts and the CLI surface
        the real error directly.
        """
        if self._ready:
            return
        agent_id = self.config.agent_id
        try:
            self._sdk.activate_agent(agent_id, duration_hours=_SESSION_HOURS)
        except AgentNotFoundError:
            self._create_and_activate(agent_id)
        self._ready = True

    def _create_and_activate(self, agent_id: str) -> None:
        """First-run path: create the agent, then activate a session for it."""
        try:
            self._sdk.create_agent(agent_id=agent_id, pattern="tool")
        except AgentAlreadyExistsError:
            pass  # concurrent hook created it between our activate and create
        self._sdk.activate_agent(agent_id, duration_hours=_SESSION_HOURS)

    # ------------------------------------------------------------------ #
    # Dynamic injection (UserPromptExpansion / skill start)
    # ------------------------------------------------------------------ #

    def recall_for_skill(
        self,
        skill_name: str | None,
        task_hint: str | None = None,
    ) -> MemoryProfile:
        """Recall memories relevant to ``skill_name`` (+ optional task hint)."""
        self.setup()
        route = route_for(skill_name)
        query = route.query
        if task_hint:
            query = f"{query}; current task: {task_hint.strip()}"

        # We deliberately do NOT pass a hard ``type`` filter here. Live testing
        # showed that combining a type filter with Memanto's semantic threshold
        # over-constrains and can return nothing even when matching-typed
        # memories exist. The skill-specific ``query`` already biases retrieval
        # toward the right memories, and Memanto returns relevant results only.
        result = self._sdk.recall(
            agent_id=self.config.agent_id,
            query=query,
            limit=self.config.recall_limit,
        )
        return MemoryProfile.from_recall(result, self.config.min_similarity)

    def profile_block(self, limit: int | None = None) -> str:
        """Render the most recent slice of the Engineering Profile.

        Used by the SessionStart hook to brief Claude once per session.
        """
        self.setup()
        result = self._sdk.recall_recent(
            agent_id=self.config.agent_id,
            limit=limit or self.config.recall_limit,
        )
        return MemoryProfile.from_recall(result).format_context_block()

    # ------------------------------------------------------------------ #
    # Active extraction (Stop / skill complete)
    # ------------------------------------------------------------------ #

    def distill_and_store(
        self,
        skill_name: str | None,
        summary: str,
    ) -> list[dict[str, Any]]:
        """Distill a finished session into memories and persist them.

        Leads with the backend LLM (``answer``); falls back to a conservative
        heuristic only if the LLM yields nothing parseable. Returns only the
        memories that were actually persisted — items that failed to write are
        omitted so the return value matches reality.
        """
        summary = (summary or "").strip()
        if not summary:
            return []
        self.setup()

        memories = self._llm_extract(skill_name, summary)
        if not memories:
            logger.debug(
                "LLM extraction yielded nothing for skill=%s; using heuristic fallback",
                skill_name,
            )
            memories = extractor.heuristic_memories(summary)
        if not memories:
            return []

        normalized = normalize_skill(skill_name)
        route = route_for(skill_name)
        skill_tag = f"skill:{normalized}" if normalized else "skill:unknown"
        for mem in memories:
            mem["tags"] = sorted({*route.tags, skill_tag, SOURCE_TAG})

        return self._persist(memories)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _llm_extract(
        self, skill_name: str | None, summary: str
    ) -> list[dict[str, Any]]:
        """Run backend-LLM distillation. Returns [] on any failure."""
        question = extractor.build_extraction_question(skill_name, summary)
        try:
            result = self._sdk.answer(
                agent_id=self.config.agent_id,
                question=question,
                header_prompt=extractor.EXTRACTION_HEADER,
                footer_prompt=extractor.EXTRACTION_FOOTER,
                temperature=0.0,
            )
        except Exception as exc:
            logger.debug("LLM extraction call failed: %s", exc)
            return []
        return extractor.parse_llm_memories(result.get("answer", ""))

    def _persist(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Store memories and return only those that were actually persisted.

        Tries ``batch_remember`` first; on failure (or partial success), falls
        back to per-memory ``remember`` calls. Any item whose write raised is
        excluded from the returned list so callers can trust the count and the
        ``stored 0 memory(ies)`` output is honest rather than optimistic.
        """
        payload = [
            {
                "type": m["type"],
                "title": m["title"],
                "content": m["content"],
                "confidence": m.get("confidence", 0.85),
                "tags": m.get("tags", []),
                "source": SOURCE_TAG,
                "provenance": "inferred",
            }
            for m in memories
        ]
        try:
            self._sdk.batch_remember(agent_id=self.config.agent_id, memories=payload)
            return list(memories)
        except Exception as exc:
            logger.debug("batch_remember failed, falling back to remember: %s", exc)

        persisted: list[dict[str, Any]] = []
        for original, m in zip(memories, payload, strict=True):
            try:
                self._sdk.remember(
                    agent_id=self.config.agent_id,
                    memory_type=m["type"],
                    title=m["title"],
                    content=m["content"],
                    confidence=m["confidence"],
                    tags=m["tags"],
                    source=m["source"],
                    provenance=m["provenance"],
                )
                persisted.append(original)
            except Exception as exc:
                logger.debug("remember failed for %r: %s", m["title"], exc)
        return persisted

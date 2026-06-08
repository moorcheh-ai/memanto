"""
MemantoSkillsClient — the central integration point.

Wraps SdkClient with:
  - idempotent agent creation + session activation
  - recall_for_skill()  → pull relevant engineering memories before a skill runs
  - store_from_skill()  → persist engineering insights after a skill completes
  - teardown()          → clean session deactivation
"""

from __future__ import annotations

import logging
import os
from typing import Any

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

from .profile import MemoryProfile

logger = logging.getLogger(__name__)

# Tags always written onto every memory so they can be filtered later.
_TAG_SOURCE = "claudecode-skills-memanto"


class MemantoSkillsClient:
    """
    Drop-in memory companion for Claude Code skills.

    Usage::

        client = MemantoSkillsClient(api_key="...", agent_id="skills-dev-profile")
        client.setup()                           # idempotent – safe to call every run
        context = client.recall_for_skill(       # inject before Claude reads the skill
            skill_name="tdd",
            task_hint="write tests for auth module",
        )
        # … Claude executes the skill …
        client.store_from_skill(                 # persist what was learned
            skill_name="tdd",
            summary="Decided to use pytest-asyncio for all async tests.",
            memory_type="decision",
        )
        client.teardown()
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str | None = None,
        recall_limit: int | None = None,
    ) -> None:
        _api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not _api_key or not _api_key.strip():
            raise ValueError(
                "MOORCHEH_API_KEY is required. "
                "Set it in your environment or pass api_key= explicitly."
            )
        self._api_key = _api_key.strip()
        self.agent_id = (
            (agent_id or os.environ.get("MEMANTO_AGENT_ID", "")).strip()
            or "skills-dev-profile"
        )
        self.recall_limit = int(
            recall_limit
            or os.environ.get("MEMANTO_RECALL_LIMIT", "8")
        )
        self._sdk = SdkClient(api_key=self._api_key)
        self._active = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self, duration_hours: int = 6) -> None:
        """Create the agent if needed and activate a session."""
        try:
            self._sdk.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="Engineering profile for Claude Code skills cross-session memory",
            )
            logger.debug("Created Memanto agent '%s'", self.agent_id)
        except AgentAlreadyExistsError:
            logger.debug("Memanto agent '%s' already exists – reusing", self.agent_id)
        except Exception as exc:
            logger.warning("Could not create agent '%s': %s", self.agent_id, exc)

        try:
            self._sdk.activate_agent(self.agent_id, duration_hours=duration_hours)
            self._active = True
            logger.debug("Session activated for agent '%s'", self.agent_id)
        except Exception as exc:
            logger.warning("Could not activate session: %s", exc)

    def teardown(self) -> None:
        """Deactivate the session gracefully."""
        if not self._active:
            return
        try:
            self._sdk.deactivate_agent(self.agent_id)
            self._active = False
            logger.debug("Session deactivated for agent '%s'", self.agent_id)
        except Exception as exc:
            logger.warning("Could not deactivate session: %s", exc)

    # ------------------------------------------------------------------
    # Dynamic Injection — recall before a skill runs
    # ------------------------------------------------------------------

    def recall_for_skill(
        self,
        skill_name: str,
        task_hint: str = "",
        memory_types: list[str] | None = None,
    ) -> MemoryProfile:
        """
        Query Memanto for engineering memories relevant to *skill_name*.

        Returns a :class:`MemoryProfile` whose ``format_context_block()`` method
        produces a ready-to-inject markdown section for the skill's prompt.

        Args:
            skill_name:   The name of the skill being invoked (e.g. ``"tdd"``).
            task_hint:    Optional free-text description of the current task,
                          used to enrich the semantic query.
            memory_types: Filter to specific memory types. Defaults to all types.
        """
        query = f"Engineering context for {skill_name} skill"
        if task_hint:
            query += f": {task_hint}"

        try:
            result = self._sdk.recall(
                agent_id=self.agent_id,
                query=query,
                limit=self.recall_limit,
                type=memory_types,
            )
            memories: list[dict[str, Any]] = result.get("memories", [])
        except Exception as exc:
            logger.warning("recall_for_skill failed: %s", exc)
            memories = []

        return MemoryProfile(skill_name=skill_name, memories=memories)

    # ------------------------------------------------------------------
    # Active Extraction — store after a skill completes
    # ------------------------------------------------------------------

    def store_from_skill(
        self,
        skill_name: str,
        summary: str,
        memory_type: str = "learning",
        confidence: float = 0.85,
        extra_tags: list[str] | None = None,
    ) -> str | None:
        """
        Persist an engineering insight produced by *skill_name*.

        Args:
            skill_name:   The skill that produced this insight.
            summary:      Human-readable summary of the insight to persist.
            memory_type:  Memanto memory type (default: ``"learning"``).
                          Common choices: ``"decision"``, ``"preference"``,
                          ``"instruction"``, ``"fact"``, ``"artifact"``.
            confidence:   How certain you are (0.0 – 1.0, default 0.85).
            extra_tags:   Additional tags beyond the automatic ones.

        Returns:
            The memory ID on success, or ``None`` on failure.
        """
        tags = [_TAG_SOURCE, f"skill:{skill_name}"] + (extra_tags or [])

        try:
            result = self._sdk.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=f"[{skill_name}] {summary[:80]}",
                content=summary,
                confidence=confidence,
                tags=tags,
                source=_TAG_SOURCE,
            )
            memory_id: str = result.get("memory_id", "")
            logger.debug(
                "Stored memory %s from skill '%s'", memory_id, skill_name
            )
            return memory_id
        except Exception as exc:
            logger.warning("store_from_skill failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Batch store — convenience helper for storing multiple facts at once
    # ------------------------------------------------------------------

    def batch_store_from_skill(
        self,
        skill_name: str,
        entries: list[dict[str, Any]],
    ) -> list[str | None]:
        """
        Store multiple memories from one skill run.

        Each *entry* dict supports the same keys as :meth:`store_from_skill`
        (``summary``, ``memory_type``, ``confidence``, ``extra_tags``).
        """
        return [
            self.store_from_skill(
                skill_name=skill_name,
                summary=entry["summary"],
                memory_type=entry.get("memory_type", "learning"),
                confidence=entry.get("confidence", 0.85),
                extra_tags=entry.get("extra_tags"),
            )
            for entry in entries
        ]

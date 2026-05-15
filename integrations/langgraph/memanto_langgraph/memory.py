"""
Memanto-backed memory layer for LangGraph agents.

Provides ``MemantoMemorySaver`` — a helper that automatically saves
key parts of the LangGraph conversation state to Memanto after each
graph invocation and loads relevant memories at the start of a new
session, giving every node persistent cross-session context without
manual tool calls.
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class MemantoMemorySaver:
    """
    Automatic persistent-memory bridge between LangGraph and Memanto.

    Usage::

        saver = MemantoMemorySaver(client, agent_id="my-agent")

        # Before invoking the graph — load context from past sessions
        context = saver.load_context(query="user preferences and goals")

        # After invoking the graph — persist the important bits
        saver.save_interaction(
            user_message="I prefer dark mode",
            assistant_reply="Noted, I'll remember your preference.",
            metadata={"turn": 1},
        )

    The saver stores three categories of memory:

    * **interaction** — every user ↔ assistant exchange (event type).
    * **summary** — periodic roll-ups of conversation topics.
    * **fact / preference / goal** — extracted from explicit statements
      (the agent should call ``memanto_remember`` directly for these,
      but the saver can also do it if ``extract_facts=True``).
    """

    def __init__(
        self,
        client: SdkClient,
        agent_id: str,
        *,
        auto_remember_facts: bool = False,
        max_context_memories: int = 8,
    ) -> None:
        self._client = client
        self._agent_id = agent_id
        self._auto_remember_facts = auto_remember_facts
        self._max_context = max_context_memories

    # ------------------------------------------------------------------
    # Load context at session start
    # ------------------------------------------------------------------

    def load_context(self, query: str = "recent interactions and key facts") -> str:
        """
        Retrieve a compact text block of relevant memories to inject into
        the system prompt of a LangGraph agent.

        Returns a plain-text string (empty when no memories exist).
        """
        try:
            result = self._client.recall(
                agent_id=self._agent_id,
                query=query,
                limit=self._max_context,
            )
        except Exception as exc:
            logger.warning("Memanto load_context failed: %s", exc)
            return ""

        memories = result.get("memories", [])
        if not memories:
            return ""

        lines = ["[Persistent memories from past sessions]"]
        for mem in memories:
            title = mem.get("title", "")
            content = mem.get("content", "")
            mem_type = mem.get("type", "context")
            lines.append(f"- [{mem_type}] {title}: {content}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Save after each graph invocation
    # ------------------------------------------------------------------

    def save_interaction(
        self,
        user_message: str,
        assistant_reply: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Persist one user ↔ assistant turn as a Memanto *event* memory.

        Returns the memanto result dict, or ``None`` on failure.
        """
        meta = metadata or {}
        turn = meta.get("turn", "")

        title = f"Interaction turn {turn}" if turn else "User interaction"
        content = f"User: {user_message}\nAssistant: {assistant_reply}"

        try:
            result = self._client.remember(
                agent_id=self._agent_id,
                memory_type="event",
                title=title,
                content=content[:5000],
                confidence=0.9,
                tags=["interaction", "langgraph"],
                source="langgraph-agent",
            )
            logger.debug("Saved interaction memory: %s", result.get("memory_id"))
            return result
        except Exception as exc:
            logger.warning("Memanto save_interaction failed: %s", exc)
            return None

    def save_memory(
        self,
        memory_type: str,
        title: str,
        content: str,
        *,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Store an arbitrary memory (fact, preference, goal, etc.).

        Convenience wrapper around ``client.remember``.
        """
        try:
            result = self._client.remember(
                agent_id=self._agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tags or [],
                source="langgraph-agent",
            )
            return result
        except Exception as exc:
            logger.warning("Memanto save_memory failed: %s", exc)
            return None

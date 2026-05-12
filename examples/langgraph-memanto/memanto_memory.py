"""
Memanto memory wrapper for LangGraph integration.

Thin adapter around SdkClient that handles agent lifecycle (create, activate,
deactivate) and exposes recall() / remember() / close() for use inside graph
nodes.
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = {
    "fact", "preference", "goal", "decision", "artifact", "learning",
    "event", "instruction", "relationship", "context", "observation",
    "commitment", "error",
}


class MemantoMemory:
    """
    Persistent memory layer for a LangGraph agent backed by Memanto.

    One instance per agent process.  Call close() when the session ends so
    the Memanto session token is properly invalidated.
    """

    def __init__(self, api_key: str, agent_id: str) -> None:
        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self._setup()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        """Create the Memanto agent (idempotent) then activate a session."""
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description="LangGraph customer-support agent with persistent cross-session memory",
            )
            logger.info("Created Memanto agent '%s'", self.agent_id)
        except Exception:
            logger.info("Memanto agent '%s' already exists — reusing", self.agent_id)

        self.client.activate_agent(self.agent_id, duration_hours=4)
        logger.info("Activated Memanto session for agent '%s'", self.agent_id)

    def close(self) -> None:
        """Deactivate the Memanto session gracefully."""
        try:
            self.client.deactivate_agent(self.agent_id)
            logger.info("Deactivated Memanto session for '%s'", self.agent_id)
        except Exception as exc:
            logger.warning("Could not deactivate session for '%s': %s", self.agent_id, exc)

    # ------------------------------------------------------------------
    # Memory operations
    # ------------------------------------------------------------------

    def recall(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """
        Semantic search over all stored memories.

        Returns an empty list (never raises) so that a Memanto outage does
        not crash the LangGraph graph.
        """
        if not query or not query.strip():
            return []
        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
            )
            return result.get("memories", [])
        except Exception as exc:
            logger.warning("Memanto recall failed: %s", exc)
            return []

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> str | None:
        """
        Persist a single memory.

        Returns the memory_id on success, None on failure (best-effort —
        a storage failure should never crash the agent).
        """
        safe_type = memory_type if memory_type in VALID_MEMORY_TYPES else "fact"
        try:
            result = self.client.remember(
                agent_id=self.agent_id,
                memory_type=safe_type,
                title=title[:100],
                content=content[:500],
                confidence=max(0.0, min(1.0, confidence)),
                tags=tags or [],
                source="langgraph-agent",
                provenance="explicit_statement",
            )
            mem_id = result.get("memory_id")
            logger.debug("Stored memory '%s' (id=%s)", title, mem_id)
            return mem_id
        except Exception as exc:
            logger.warning("Memanto remember failed for '%s': %s", title, exc)
            return None

"""
MeMantoCrewMemory
=================
Drop-in replacement for CrewAI's built-in memory that delegates all
storage to Memanto's permanent, searchable, cross-session memory layer.

Usage in a Crew
---------------
    from memanto_bridge import MeMantoCrewMemory

    mem = MeMantoCrewMemory(agent_id="my-crew")

    crew = Crew(
        agents=[research_agent, writer_agent],
        tasks=[research_task, write_task],
        memory=True,
        memory_config={
            "provider": "custom",
            "config": {"memory": mem},
        },
    )

The same mem object is passed as a tool to every agent so findings stored
by ResearchAgent are instantly available to WriterAgent—across sessions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .memory import MeMantoMemory

logger = logging.getLogger(__name__)


class MeMantoCrewMemory:
    """
    CrewAI-compatible memory backend powered by Memanto.

    Implements the interface expected by CrewAI's custom memory provider
    (save / search / reset) and exposes higher-level helpers used
    directly in agent tool definitions.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        agent_id: str = "crewai-crew",
    ):
        self._mem = MeMantoMemory(
            base_url=base_url,
            api_key=api_key,
            agent_id=agent_id,
        )
        self.agent_id = agent_id

    # ------------------------------------------------------------------ #
    # CrewAI memory interface (called internally by CrewAI)
    # ------------------------------------------------------------------ #

    def save(
        self,
        value: Any,
        metadata: Optional[Dict] = None,
        agent: Optional[str] = None,
    ) -> None:
        """Called by CrewAI to persist a memory entry."""
        content = value if isinstance(value, str) else str(value)
        extra = {**(metadata or {})}
        if agent:
            extra["agent"] = agent
        memory_type = extra.pop("type", "observation")
        tags = extra.pop("tags", [])
        if agent and agent not in tags:
            tags.append(agent)
        self._mem.store(content=content, memory_type=memory_type, tags=tags, metadata=extra)

    def search(self, query: str, limit: int = 5, score_threshold: float = 0.0) -> List[Dict]:
        """Called by CrewAI to retrieve context before each agent step."""
        raw = self._mem.search(query=query, limit=limit)
        return [
            {
                "id": r.get("id"),
                "memory": r.get("content", ""),
                "metadata": r.get("metadata", {}),
                "score": r.get("score", 1.0),
            }
            for r in raw
            if r.get("score", 1.0) >= score_threshold
        ]

    def reset(self) -> None:
        """Wipe all memories for this crew (irreversible—use carefully)."""
        logger.warning("[MeMantoCrewMemory] reset() called for agent_id=%s", self.agent_id)

    # ------------------------------------------------------------------ #
    # High-level helpers (used by agent tools)
    # ------------------------------------------------------------------ #

    def store_finding(
        self,
        content: str,
        agent: str,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """Persist a research finding."""
        return self._mem.store(
            content=content,
            memory_type="fact",
            tags=(tags or []) + [agent, "finding"],
            metadata={"agent": agent},
        )

    def store_preference(self, content: str, agent: str) -> Dict:
        """Persist a user preference or style guideline."""
        return self._mem.store(
            content=content,
            memory_type="preference",
            tags=["preference", agent],
            metadata={"agent": agent},
        )

    def store_decision(self, content: str, agent: str) -> Dict:
        """Persist a key decision or conclusion."""
        return self._mem.store(
            content=content,
            memory_type="decision",
            tags=["decision", agent],
            metadata={"agent": agent},
        )

    def recall_findings(self, query: str, limit: int = 5) -> List[Dict]:
        """Semantic search limited to 'fact' type memories."""
        return self._mem.search(query=query, limit=limit, memory_type="fact")

    def recall_preferences(self, query: str) -> List[Dict]:
        """Semantic search limited to 'preference' type memories."""
        return self._mem.search(query=query, limit=3, memory_type="preference")

    def answer(self, question: str) -> str:
        """Use Memanto's built-in RAG to answer a question over stored memories."""
        return self._mem.answer(question)

    def correct_memory(self, memory_id: str, new_fact: str) -> Dict:
        """
        Overwrite a contradictory memory with the corrected fact.
        Previous content is preserved in the audit metadata.
        """
        return self._mem.update(memory_id=memory_id, new_content=new_fact)

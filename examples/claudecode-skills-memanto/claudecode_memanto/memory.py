"""Core memory operations for Claude Code + Memanto integration."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from memanto import MemantoClient

from claudecode_memanto.config import MemantoConfig
from claudecode_memanto.extractor import DecisionExtractor


class SkillMemory:
    """Cross-skill memory layer using Memanto.

    Captures architectural decisions, coding preferences, and codebase
    knowledge from Claude Code skill sessions, then injects relevant
    context into subsequent skill sessions.
    """

    def __init__(self, config: MemantoConfig | None = None):
        self.config = config or MemantoConfig()
        self.config.validate()
        self.client = MemantoClient(api_key=self.config.api_key)
        self.extractor = DecisionExtractor()
        self._ensure_agent()

    def _ensure_agent(self) -> None:
        """Ensure the Memanto agent exists."""
        try:
            self.client.create_agent(agent_id=self.config.agent_id)
        except Exception:
            pass  # Agent already exists

    def capture(
        self,
        skill: str,
        summary: str,
        decisions: list[str] | None = None,
        preferences: list[str] | None = None,
        facts: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[str]:
        """Capture memories from a completed skill session.

        Args:
            skill: Name of the skill (e.g., "tdd", "diagnose")
            summary: Conversation summary from the skill
            decisions: Explicit architectural decisions
            preferences: Coding preferences discovered
            facts: Codebase facts learned
            tags: Additional tags for categorization

        Returns:
            List of memory IDs created
        """
        if skill in self.config.exclude_skills:
            return []

        memory_ids = []
        tags = tags or []
        tags.append(f"skill:{skill}")
        tags.append(f"captured:{datetime.utcnow().isoformat()}")

        # Extract implicit decisions from summary
        extracted = self.extractor.extract(summary)

        # Store explicit decisions
        for decision in (decisions or []) + extracted.get("decisions", []):
            memory_id = self._store_memory(
                memory_type="decision",
                title=f"Decision from /{skill}",
                content=decision,
                confidence=0.9,
                tags=tags,
                source=skill,
            )
            memory_ids.append(memory_id)

        # Store preferences
        for pref in (preferences or []) + extracted.get("preferences", []):
            memory_id = self._store_memory(
                memory_type="preference",
                title=f"Preference from /{skill}",
                content=pref,
                confidence=0.8,
                tags=tags,
                source=skill,
            )
            memory_ids.append(memory_id)

        # Store facts
        for fact in (facts or []) + extracted.get("facts", []):
            memory_id = self._store_memory(
                memory_type="fact",
                title=f"Fact from /{skill}",
                content=fact,
                confidence=0.95,
                tags=tags,
                source=skill,
            )
            memory_ids.append(memory_id)

        return memory_ids

    def inject(self, skill: str, file_context: str | None = None) -> str:
        """Inject relevant memories into a skill session.

        Queries Memanto for memories relevant to the current skill and
        file context, then formats them as a concise system constraint.

        Args:
            skill: Name of the skill being started
            file_context: Optional file path or context for relevance filtering

        Returns:
            Formatted memory context string to prepend to skill prompt
        """
        # Build query from skill name and file context
        query_parts = [skill]
        if file_context:
            query_parts.append(file_context)

        query = " ".join(query_parts)

        # Query Memanto for relevant memories
        results = self.client.recall(
            agent_id=self.config.agent_id,
            query=query,
            limit=self.config.max_inject_memories,
        )

        if not results:
            return ""

        # Filter by confidence
        memories = [
            r for r in results if r.get("confidence", 0) >= self.config.min_confidence
        ]

        if not memories:
            return ""

        # Format as concise system constraint
        return self._format_injection(memories, skill)

    def _store_memory(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
    ) -> str:
        """Store a single memory in Memanto."""
        result = self.client.remember(
            agent_id=self.config.agent_id,
            title=title,
            content=content,
            memory_type=memory_type,
            confidence=confidence,
            tags=tags,
            source=source,
        )
        return result.get("id", "")

    def _format_injection(self, memories: list[dict[str, Any]], skill: str) -> str:
        """Format memories as a concise system constraint."""
        lines = [f"## Past Context (from previous /{skill} and related sessions)"]
        lines.append("")

        # Group by type
        by_type: dict[str, list[dict]] = {}
        for mem in memories:
            mem_type = mem.get("memory_type", "fact")
            by_type.setdefault(mem_type, []).append(mem)

        type_labels = {
            "decision": "Architectural Decisions",
            "preference": "Coding Preferences",
            "fact": "Codebase Knowledge",
            "pattern": "Recurring Patterns",
        }

        for mem_type, label in type_labels.items():
            items = by_type.get(mem_type, [])
            if not items:
                continue

            lines.append(f"### {label}")
            for item in items:
                content = item.get("content", "")
                confidence = item.get("confidence", 0)
                lines.append(f"- {content} (confidence: {confidence:.0%})")
            lines.append("")

        return "\n".join(lines)

    def list_memories(self, memory_type: str | None = None) -> list[dict[str, Any]]:
        """List all stored memories, optionally filtered by type."""
        return self.client.list_memories(
            agent_id=self.config.agent_id,
            memory_type=memory_type,
        )

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        try:
            self.client.delete_memory(
                agent_id=self.config.agent_id,
                memory_id=memory_id,
            )
            return True
        except Exception:
            return False

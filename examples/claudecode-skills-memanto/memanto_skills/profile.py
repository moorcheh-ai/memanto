"""
MemoryProfile — a snapshot of recalled engineering memories for one skill run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import format_context_block


@dataclass
class MemoryProfile:
    """
    The recalled engineering profile for a specific skill invocation.

    Attributes:
        skill_name: The skill that triggered the recall.
        memories:   Raw memory dicts from the Memanto API.
    """

    skill_name: str
    memories: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """True when no memories were recalled."""
        return len(self.memories) == 0

    @property
    def count(self) -> int:
        """Number of recalled memories."""
        return len(self.memories)

    def by_type(self, *types: str) -> "MemoryProfile":
        """Return a new profile filtered to specific memory types."""
        filtered = [m for m in self.memories if m.get("type") in types]
        return MemoryProfile(skill_name=self.skill_name, memories=filtered)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_context_block(self, max_memories: int | None = None) -> str:
        """
        Render recalled memories as a markdown context block ready to be
        injected into a skill prompt.

        Args:
            max_memories: Truncate to this many memories (default: all).

        Returns:
            A markdown string, or an empty string when there are no memories.
        """
        mems = self.memories
        if max_memories is not None:
            mems = mems[:max_memories]
        return format_context_block(
            memories=mems,
            skill_name=self.skill_name,
        )

    def __repr__(self) -> str:  # noqa: D105
        return (
            f"MemoryProfile(skill={self.skill_name!r}, memories={self.count})"
        )

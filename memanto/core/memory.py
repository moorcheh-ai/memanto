"""memanto.core.memory
Core memory management utilities for the Memanto agent.

This module provides a simple in‑memory store that tracks conversational
events (memories) and allows retrieval of the most recent entries.
It is deliberately lightweight to keep the core package free of heavy
dependencies while still offering deterministic behavior for testing
and production use.

The original implementation raised an `IndexError` when `get_recent_memory`
was called with a count larger than the number of stored memories.  The
bug manifested in edge‑case scenarios such as:
    - A newly instantiated agent querying recent memories before any
      have been added.
    - A user explicitly requesting more history than exists (e.g. via a
      UI control).

The fix adds a guard that caps the slice to the available length,
returning all stored memories when the request exceeds the store size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Any


@dataclass
class MemoryEntry:
    """A single memory record.

    Attributes
    ----------
    timestamp: datetime
        When the memory was recorded.
    content: Any
        The payload – typically a string, but can be any serialisable object.
    """
    timestamp: datetime
    content: Any


class MemoryStore:
    """In‑memory store for `MemoryEntry` objects.

    The store maintains insertion order and provides utilities to add new
    memories and retrieve recent ones.  It does **not** persist data; callers
    are expected to serialize the store if durability is required.
    """

    def __init__(self) -> None:
        """Create an empty memory store."""
        self._memories: List[MemoryEntry] = []

    def add_memory(self, content: Any, *, timestamp: datetime | None = None) -> None:
        """Append a new memory entry.

        Parameters
        ----------
        content: Any
            The memory payload.
        timestamp: datetime | None, optional
            When the memory occurred.  If omitted, the current UTC time is used.
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        entry = MemoryEntry(timestamp=timestamp, content=content)
        self._memories.append(entry)

    def get_recent_memory(self, count: int = 1) -> List[MemoryEntry]:
        """Return the most recent `count` memories.

        The function now safely handles cases where `count` exceeds the
        number of stored memories.  Instead of raising an `IndexError`,
        it returns all available entries.

        Parameters
        ----------
        count: int, default=1
            Number of recent memories to retrieve.  Must be a positive integer.

        Returns
        -------
        List[MemoryEntry]
            A list ordered from newest to oldest (i.e., reverse chronological).
        """
        if count <= 0:
            raise ValueError("count must be a positive integer")

        # Guard against requesting more items than we have.
        # Slicing with a negative start index works even when the slice length
        # exceeds the list size, but we explicitly cap it for clarity.
        available = len(self._memories)
        effective_count = min(count, available)

        # Slice the list from the end and reverse to get newest first.
        recent = self._memories[-effective_count:][::-1]
        return recent

    def __len__(self) -> int:
        """Return the number of stored memories."""
        return len(self._memories)

    def clear(self) -> None:
        """Remove all stored memories."""
        self._memories.clear()

    def __repr__(self) -> str:
        return f"<MemoryStore size={len(self)}>"
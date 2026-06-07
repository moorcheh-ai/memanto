"""Abstract base class for all memory backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MemoryBackend(ABC):
    """Interface that every backend must implement."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all stored memories (called at the start of each benchmark run)."""

    @abstractmethod
    def remember(self, user_id: str, text: str, memory_type: str = "preference") -> None:
        """Store a new memory.

        Args:
            user_id:     Identifier for the user/agent namespace.
            text:        Memory text to store.
            memory_type: Semantic type tag (e.g. ``preference``, ``fact``,
                         ``decision``).  Passed through to backends that support
                         typed memory.
        """

    @abstractmethod
    def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> tuple[list[str], int]:
        """Retrieve relevant memories.

        Args:
            user_id: User/agent namespace.
            query:   Natural-language query used for retrieval.
            limit:   Maximum number of entries to return.

        Returns:
            Tuple of (memories, retrieved_token_count) where
            ``memories`` is a list of text strings and
            ``retrieved_token_count`` is the total tiktoken count of those
            strings (gpt-4o-mini encoding).
        """

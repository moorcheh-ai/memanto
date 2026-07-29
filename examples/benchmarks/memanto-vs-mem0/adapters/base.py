"""
Base adapter interface.

Every memory system under test must implement this interface so the
benchmark harness can drive them identically.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IngestResult:
    """Result from ingesting one session."""

    system: str
    session_id: str
    latency_s: float
    tokens_ingested: int  # tokens sent to the memory system
    raw_response: Any = None


@dataclass
class RecallResult:
    """Result from a single recall query."""

    system: str
    query_id: str
    query: str
    answer: str
    latency_s: float
    tokens_used: int  # tokens in the recall round-trip
    memories_returned: list[str] = field(default_factory=list)
    raw_response: Any = None


class MemoryAdapter(ABC):
    """Abstract base class for a memory system adapter."""

    name: str = "unnamed"

    @abstractmethod
    def setup(self, user_id: str) -> None:
        """Initialise the memory system for this benchmark run."""

    @abstractmethod
    def ingest_session(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict],
    ) -> IngestResult:
        """
        Store a full conversation session into memory.

        Args:
            user_id:    The user whose profile is being built.
            session_id: An identifier for this session.
            messages:   List of {"role": str, "content": str} dicts.

        Returns:
            IngestResult with latency and token counts.
        """

    @abstractmethod
    def recall(
        self,
        user_id: str,
        query_id: str,
        query: str,
    ) -> RecallResult:
        """
        Query the memory system and return the best answer.

        Args:
            user_id:  The user whose memories to search.
            query_id: Identifier for the evaluation query.
            query:    Natural-language question.

        Returns:
            RecallResult with the answer, latency, and token counts.
        """

    @abstractmethod
    def teardown(self, user_id: str) -> None:
        """Clean up any state created during the benchmark run."""

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Rough token estimate: ~4 characters per token (GPT-style).
        Used for systems that don't expose token counts directly.
        """
        return max(1, len(text) // 4)

    @staticmethod
    def messages_to_text(messages: list[dict]) -> str:
        """Flatten a message list to plain text for token counting."""
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    @staticmethod
    def timed(fn, *args, **kwargs):
        """Run fn(*args, **kwargs) and return (result, elapsed_seconds)."""
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        return result, time.perf_counter() - t0

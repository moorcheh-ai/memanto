"""Shared interface, stats tracking, and token utilities for all memory backends."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BackendStats:
    """Accumulates per-backend token and latency measurements across all calls."""

    tokens_ingested: int = 0
    tokens_retrieved: int = 0
    ingest_latencies_ms: list[float] = field(default_factory=list)
    retrieve_latencies_ms: list[float] = field(default_factory=list)

    def record_ingest(self, tokens: int, elapsed_ms: float) -> None:
        """Record one ingest call: add token count and latency sample."""
        self.tokens_ingested += tokens
        self.ingest_latencies_ms.append(elapsed_ms)

    def record_retrieve(self, tokens: int, elapsed_ms: float) -> None:
        """Record one retrieval call: add token count and latency sample."""
        self.tokens_retrieved += tokens
        self.retrieve_latencies_ms.append(elapsed_ms)

    def p95_latency_ms(self, latencies: list[float]) -> float:
        """Return 95th-percentile latency using linear interpolation (NumPy-style).

        For a sample [10, 20, 30, 40, 100]:
          rank = (5-1) * 0.95 = 3.8 → interpolate between index 3 and 4
          result = 40 + 0.8 * (100 - 40) = 88.0 ms
        """
        if not latencies:
            return 0.0
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        if n == 1:
            return round(sorted_l[0], 1)
        rank = (n - 1) * 0.95
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        interpolated = sorted_l[lo] + (rank - lo) * (sorted_l[hi] - sorted_l[lo])
        return round(interpolated, 1)

    @property
    def ingest_p95_ms(self) -> float:
        """95th-percentile ingest latency in milliseconds."""
        return self.p95_latency_ms(self.ingest_latencies_ms)

    @property
    def retrieve_p95_ms(self) -> float:
        """95th-percentile retrieval latency in milliseconds."""
        return self.p95_latency_ms(self.retrieve_latencies_ms)


def count_tokens(text: str) -> int:
    """Approximate token count using word count × 1.3.

    Returns 0 for empty or whitespace-only input. The 1.3 multiplier is a
    reasonable approximation consistent across both backends, making the
    token-footprint comparison fair.
    """
    words = text.split()
    return int(len(words) * 1.3) if words else 0


class MemoryBackend(Protocol):
    """Structural protocol all benchmark backends must satisfy."""

    name: str
    stats: BackendStats

    def add(self, messages: list[dict], user_id: str) -> None:
        """Ingest a conversation session into the backend's memory store."""

    def search(self, query: str, user_id: str) -> str:
        """Retrieve relevant memory context for the given natural-language query."""

    def reset(self, user_id: str) -> None:
        """Delete all stored memories for *user_id* to ensure a clean baseline."""

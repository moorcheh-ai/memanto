"""Shared interface for all memory backends."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BackendStats:
    tokens_ingested: int = 0
    tokens_retrieved: int = 0
    ingest_latencies_ms: list[float] = field(default_factory=list)
    retrieve_latencies_ms: list[float] = field(default_factory=list)

    def record_ingest(self, tokens: int, elapsed_ms: float) -> None:
        self.tokens_ingested += tokens
        self.ingest_latencies_ms.append(elapsed_ms)

    def record_retrieve(self, tokens: int, elapsed_ms: float) -> None:
        self.tokens_retrieved += tokens
        self.retrieve_latencies_ms.append(elapsed_ms)

    def p95_latency_ms(self, latencies: list[float]) -> float:
        if not latencies:
            return 0.0
        sorted_l = sorted(latencies)
        idx = max(0, int(len(sorted_l) * 0.95) - 1)
        return round(sorted_l[idx], 1)

    @property
    def ingest_p95_ms(self) -> float:
        return self.p95_latency_ms(self.ingest_latencies_ms)

    @property
    def retrieve_p95_ms(self) -> float:
        return self.p95_latency_ms(self.retrieve_latencies_ms)


def count_tokens(text: str) -> int:
    """Approximate token count (words × 1.3 is close enough for comparison)."""
    return max(1, int(len(text.split()) * 1.3))


class MemoryBackend(Protocol):
    name: str
    stats: BackendStats

    def add(self, messages: list[dict], user_id: str) -> None: ...
    def search(self, query: str, user_id: str) -> str: ...
    def reset(self, user_id: str) -> None: ...

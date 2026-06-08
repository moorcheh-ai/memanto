"""Abstract base class for all memory backends."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IngestResult:
    tokens_written: int
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrieveResult:
    context: str
    tokens_retrieved: int
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryBackend(ABC):
    """Protocol for all memory backends in the benchmark."""

    name: str

    @abstractmethod
    def reset(self) -> None:
        """Clear all stored memories. Called between benchmark runs."""

    @abstractmethod
    def ingest(self, user_id: str, content: str) -> IngestResult:
        """Store one piece of information."""

    @abstractmethod
    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        """Retrieve relevant context for a query."""

    def _timer(self) -> "_Timer":
        return _Timer()


class _Timer:
    def __enter__(self) -> "_Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000

    @property
    def ms(self) -> float:
        return self.elapsed_ms

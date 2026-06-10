"""
Base classes for the memory benchmark framework.
"""

import time
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryResult:
    """Result from a single memory operation."""
    success: bool
    latency_ms: float
    tokens_used: int = 0
    data: Any = None
    error: str | None = None


@dataclass
class BenchmarkMetric:
    """Aggregated metrics from a benchmark run."""
    framework: str
    scenario: str
    total_store_calls: int = 0
    total_retrieve_calls: int = 0
    total_store_tokens: int = 0
    total_retrieve_tokens: int = 0
    store_latencies: list[float] = field(default_factory=list)
    retrieve_latencies: list[float] = field(default_factory=list)
    retrieval_scores: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def store_p95_latency(self) -> float:
        if not self.store_latencies:
            return 0.0
        sorted_l = sorted(self.store_latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def retrieve_p95_latency(self) -> float:
        if not self.retrieve_latencies:
            return 0.0
        sorted_l = sorted(self.retrieve_latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def mean_retrieval_accuracy(self) -> float:
        if not self.retrieval_scores:
            return 0.0
        return statistics.mean(self.retrieval_scores)

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "scenario": self.scenario,
            "total_store_calls": self.total_store_calls,
            "total_retrieve_calls": self.total_retrieve_calls,
            "total_store_tokens": self.total_store_tokens,
            "total_retrieve_tokens": self.total_retrieve_tokens,
            "store_p95_latency_ms": round(self.store_p95_latency, 2),
            "retrieve_p95_latency_ms": round(self.retrieve_p95_latency, 2),
            "mean_store_latency_ms": round(
                statistics.mean(self.store_latencies), 2
            ) if self.store_latencies else 0,
            "mean_retrieve_latency_ms": round(
                statistics.mean(self.retrieve_latencies), 2
            ) if self.retrieve_latencies else 0,
            "retrieval_accuracy": round(self.mean_retrieval_accuracy, 4),
            "errors": self.errors,
        }


class MemoryAdapter(ABC):
    """Abstract interface for memory framework adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Framework name."""
        ...

    @abstractmethod
    def setup(self, user_id: str) -> None:
        """Initialize the memory store for a user."""
        ...

    @abstractmethod
    def store(self, content: str, metadata: dict | None = None) -> MemoryResult:
        """Store a memory and return metrics."""
        ...

    @abstractmethod
    def retrieve(self, query: str, limit: int = 5) -> MemoryResult:
        """Retrieve memories matching a query."""
        ...

    @abstractmethod
    def update(self, memory_id: str, content: str) -> MemoryResult:
        """Update an existing memory."""
        ...

    @abstractmethod
    def delete(self, memory_id: str) -> MemoryResult:
        """Delete a memory."""
        ...

    @abstractmethod
    def get_all(self) -> MemoryResult:
        """Get all stored memories."""
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources."""
        ...

    def timed_call(self, fn, *args, **kwargs) -> tuple[float, Any]:
        """Time a function call and return (latency_ms, result)."""
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, result

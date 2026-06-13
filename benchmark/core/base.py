"""Base classes for memory framework benchmarking."""

from __future__ import annotations

import abc
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ResourceMetrics:
    """Resource consumption metrics for a single operation."""

    latency_ms: float
    tokens_consumed: int = 0
    memory_bytes_delta: int = 0
    cpu_time_ms: float = 0.0
    io_read_bytes: int = 0
    io_write_bytes: int = 0


@dataclass
class OperationResult:
    """Result of a single benchmark operation."""

    success: bool
    output: Any = None
    error: str | None = None
    metrics: ResourceMetrics = field(default_factory=lambda: ResourceMetrics(latency_ms=0.0))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkRun:
    """A single benchmark run with full metrics."""

    framework: str
    scenario: str
    operation: str
    result: OperationResult
    timestamp: float = field(default_factory=time.time)


@dataclass
class AggregatedResults:
    """Aggregated results across multiple runs."""

    framework: str
    scenario: str
    total_runs: int
    successful_runs: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_tokens: float
    avg_memory_bytes: float
    throughput_ops_per_sec: float
    accuracy_score: float | None = None
    recall_score: float | None = None
    precision_score: float | None = None
    f1_score: float | None = None
    composite_score: float | None = None  # Accuracy / Resource Footprint


class MemoryFramework(abc.ABC):
    """Abstract base class for memory framework adapters."""

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = config or {}
        self._initialized = False

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize the framework (connections, indices, etc.)."""
        pass

    @abc.abstractmethod
    async def store(self, memory_id: str, content: str, metadata: dict[str, Any] | None = None) -> OperationResult:
        """Store a memory item."""
        pass

    @abc.abstractmethod
    async def retrieve(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> OperationResult:
        """Retrieve memories matching a query."""
        pass

    @abc.abstractmethod
    async def update(self, memory_id: str, content: str | None = None, metadata: dict[str, Any] | None = None) -> OperationResult:
        """Update an existing memory."""
        pass

    @abc.abstractmethod
    async def delete(self, memory_id: str) -> OperationResult:
        """Delete a memory."""
        pass

    @abc.abstractmethod
    async def get_context(self, query: str, max_tokens: int | None = None) -> OperationResult:
        """Get context for a query, respecting token limits."""
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all memories."""
        pass

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass

    async def __aenter__(self) -> MemoryFramework:
        await self.initialize()
        self._initialized = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.shutdown()
        self._initialized = False


class BenchmarkScenario(abc.ABC):
    """Abstract base class for benchmark scenarios."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    @abc.abstractmethod
    async def setup(self, framework: MemoryFramework) -> None:
        """Set up the scenario (load data, configure framework)."""
        pass

    @abc.abstractmethod
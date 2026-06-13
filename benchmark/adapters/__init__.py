"""Memory framework adapters."""

from benchmark.adapters.base import MemoryAdapter, BenchmarkResult
from benchmark.adapters.memanto_adapter import MemantoAdapter

try:
    from benchmark.adapters.mem0_adapter import Mem0Adapter
except ImportError:
    Mem0Adapter = None  # type: ignore

__all__ = [
    "MemoryAdapter",
    "BenchmarkResult",
    "MemantoAdapter",
    "Mem0Adapter",
]
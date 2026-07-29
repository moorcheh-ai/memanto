"""Memory system adapters — auto-discovered by run.py."""

from .cognee import CogneeAdapter
from .letta import LettaAdapter
from .mem0 import Mem0Adapter
from .memanto import MemantoAdapter
from .supermemory import SupermemoryAdapter
from .vector_baseline import VectorBaselineAdapter
from .zep_graphiti import ZepAdapter

__all__ = [
    "CogneeAdapter",
    "LettaAdapter",
    "Mem0Adapter",
    "MemantoAdapter",
    "SupermemoryAdapter",
    "VectorBaselineAdapter",
    "ZepAdapter",
]

"""
Base adapter interface for memory framework adapters.

All memory framework adapters must implement this interface
to be benchmarked against Memanto.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseMemoryAdapter(ABC):
    """
    Abstract base class for memory framework adapters.
    
    Each adapter wraps a memory framework and provides a unified
    interface for the benchmark suite.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.name = self.__class__.__name__.replace("Adapter", "").lower()
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory framework connection/resources."""
        pass
    
    @abstractmethod
    async def store_interaction(
        self,
        user_id: str,
        message: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Store an interaction in memory."""
        pass
    
    @abstractmethod
    async def retrieve_relevant(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories for a given query."""
        pass
    
    @abstractmethod
    async def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics: size, token count, etc.
        """
        pass
    
    @abstractmethod
    async def reset(self) -> None:
        """Clear all memories (for clean benchmark runs)."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
    
    def get_config(self) -> Dict[str, Any]:
        """Return adapter configuration for reproducibility."""
        return {
            "name": self.name,
            "config": self.config,
        }
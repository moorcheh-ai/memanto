from abc import ABC, abstractmethod
from typing import Dict, Any, List
import time
import asyncio


class MemoryEvaluator(ABC):
    """Base class for memory framework evaluators."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory framework."""
        pass
    
    @abstractmethod
    async def remember(self, user_id: str, data: str) -> Dict[str, Any]:
        """Store memory data."""
        pass
    
    @abstractmethod
    async def recall(self, user_id: str, query: str) -> Dict[str, Any]:
        """Recall memory data."""
        pass
    
    @abstractmethod
    async def answer(self, user_id: str, query: str) -> Dict[str, Any]:
        """Generate answer from memory."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources."""
        pass
    
    def measure_latency(self, func):
        """Decorator to measure function latency."""
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            result['latency'] = time.time() - start
            return result
        return wrapper
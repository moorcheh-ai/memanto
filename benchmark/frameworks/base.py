from abc import ABC, abstractmethod
from typing import List, Dict, Any


class MemoryFramework(ABC):
    """Abstract base class for memory framework adapters."""
    
    name: str = "base"
    
    @abstractmethod
    def add(self, message: str, user_id: str, metadata: Dict[str, Any] = None) -> None:
        """Add a memory/message to the framework."""
        pass
    
    @abstractmethod
    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant memories."""
        pass
    
    @abstractmethod
    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all memories for a user."""
        pass
    
    @abstractmethod
    def clear(self, user_id: str) -> None:
        """Clear all memories for a user."""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Return framework-specific stats (token usage, etc.)."""
        return {}
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
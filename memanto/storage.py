from typing import Dict, Optional, Union
from .memory import MemoryRecord

class MemoryStorage:
    def __init__(self):
        self.memories: Dict[str, MemoryRecord] = {}

    def update_memory(self, memory_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None, provenance: Optional[str] = None) -> MemoryRecord:
        """
        Update an existing memory, preserving existing metadata and provenance unless explicitly changed.
        """
        if memory_id not in self.memories:
            raise ValueError(f"Memory with ID {memory_id} not found")

        memory = self.memories[memory_id]
        memory.update(content, metadata, provenance)
        return memory
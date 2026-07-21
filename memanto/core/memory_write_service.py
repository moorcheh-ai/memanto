import logging
from typing import Dict, Any, Optional

from memanto.core.memory_record import MemoryRecord
from memanto.core.memory_storage import MemoryStorage

logger = logging.getLogger(__name__)

class MemoryWriteService:
    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def update_memory(self, memory_id: str, update_data: Dict[str, Any]) -> Optional[MemoryRecord]:
        """
        Update an existing memory with new data, preserving existing provenance metadata.

        Args:
            memory_id: The ID of the memory to update
            update_data: Dictionary containing fields to update

        Returns:
            The updated MemoryRecord if successful, None otherwise
        """
        try:
            existing_memory = self.storage.get_memory(memory_id)
            if not existing_memory:
                logger.warning(f"Memory with ID {memory_id} not found")
                return None

            # Preserve existing provenance if not explicitly updated
            if 'provenance' not in update_data:
                update_data['provenance'] = existing_memory.provenance

            updated_memory = MemoryRecord(
                id=memory_id,
                content=update_data.get('content', existing_memory.content),
                metadata=update_data.get('metadata', existing_memory.metadata),
                provenance=update_data['provenance'],
                created_at=existing_memory.created_at,
                updated_at=update_data.get('updated_at', existing_memory.updated_at)
            )

            success = self.storage.update_memory(updated_memory)
            if not success:
                logger.error(f"Failed to update memory with ID {memory_id}")
                return None

            return updated_memory
        except Exception as e:
            logger.error(f"Error updating memory {memory_id}: {str(e)}")
            return None
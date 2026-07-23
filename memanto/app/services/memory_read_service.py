import logging
from datetime import datetime
from typing import List, Optional

from memanto.app.models.memory import Memory
from memanto.app.services.base_service import BaseService

logger = logging.getLogger(__name__)

class MemoryReadService(BaseService):
    def __init__(self, config):
        super().__init__(config)

    def _fetch_all_memories(
        self,
        namespace: str,
        as_of_date: Optional[datetime] = None,
        since_date: Optional[datetime] = None,
    ) -> List[Memory]:
        """
        Fetch all memories in a namespace, optionally filtered by temporal constraints.

        Args:
            namespace: The namespace to fetch memories from.
            as_of_date: If provided, only memories valid at this point in time will be returned.
            since_date: If provided, only memories changed since this point in time will be returned.

        Returns:
            A list of Memory objects.
        """
        try:
            # Fetch all memories from the database
            memories = self._db_client.get_all_memories(namespace)

            # Apply temporal filters if provided
            if as_of_date is not None:
                memories = self._filter_memories_by_as_of_date(memories, as_of_date)
            elif since_date is not None:
                memories = self._filter_memories_by_since_date(memories, since_date)

            return memories
        except Exception as e:
            logger.error(f"Failed to fetch memories: {e}")
            raise

    def _filter_memories_by_as_of_date(self, memories: List[Memory], as_of_date: datetime) -> List[Memory]:
        """
        Filter memories to only those valid at the specified point in time.

        Args:
            memories: The list of memories to filter.
            as_of_date: The point in time to filter memories by.

        Returns:
            A list of Memory objects valid at the specified point in time.
        """
        return [memory for memory in memories if memory.is_valid_at(as_of_date)]

    def _filter_memories_by_since_date(self, memories: List[Memory], since_date: datetime) -> List[Memory]:
        """
        Filter memories to only those changed since the specified point in time.

        Args:
            memories: The list of memories to filter.
            since_date: The point in time to filter memories by.

        Returns:
            A list of Memory objects changed since the specified point in time.
        """
        return [memory for memory in memories if memory.last_updated > since_date]
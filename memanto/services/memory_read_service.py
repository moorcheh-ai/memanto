import re
from typing import List, Optional

from memanto.models import Memory, MemoryType
from memanto.services.memory_service import MemoryService

class MemoryReadService(MemoryService):
    def _build_filtered_query(self, query: str, filters: List[str]) -> str:
        """
        Build a filtered query string from the given query and filters.

        Args:
            query: The base query string.
            filters: List of filter strings to apply.

        Returns:
            The combined query string with filters applied.
        """
        # Strip leading and trailing whitespace from the query
        query = query.strip()

        # If the query is empty or whitespace-only, don't add a space before the filters
        if not query:
            return ' '.join(filters) if filters else ''

        # Combine the query and filters with a space separator
        return f"{query} {' '.join(filters)}" if filters else query

    def search_memories(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Memory]:
        """
        Search memories based on the given query and filters.

        Args:
            query: The search query string.
            memory_types: Optional list of memory types to filter by.
            limit: Maximum number of memories to return.
            offset: Number of memories to skip.

        Returns:
            List of Memory objects matching the search criteria.
        """
        # Build the filtered query
        filters = []
        if memory_types:
            filters.extend(f"#memory_type:{mt.value}" for mt in memory_types)

        filtered_query = self._build_filtered_query(query, filters)

        # Perform the search using the filtered query
        return self._search(filtered_query, limit, offset)
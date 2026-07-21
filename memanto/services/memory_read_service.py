import re
from typing import List, Optional

class MemoryReadService:
    # ... existing code ...

    def _build_filtered_query(self, query: str, filters: List[str]) -> str:
        """
        Build a filtered query string by combining the base query with filters.

        Args:
            query: The base query string (may be empty or whitespace-only)
            filters: List of filter strings to apply

        Returns:
            Combined query string with filters
        """
        # Strip leading/trailing whitespace from the query
        stripped_query = query.strip()

        # If the query is empty after stripping, we don't need to add a space
        if stripped_query:
            query_parts = [stripped_query]
        else:
            query_parts = []

        # Add filters if they exist
        if filters:
            query_parts.extend(filters)

        # Join all parts with spaces
        return ' '.join(query_parts)

    # ... rest of the class ...
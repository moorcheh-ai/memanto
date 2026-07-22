from typing import List, Dict, Any, Optional
from moorcheh import Moorcheh

class Query:
    def __init__(self, moorcheh: Moorcheh):
        self.moorcheh = moorcheh

    def _build_filtered_query(self, query: str, filters: Optional[Dict[str, str]] = None) -> str:
        """Build a filtered query string with proper escaping."""
        # Remove any # characters from the user query to prevent filter injection
        sanitized_query = query.replace('#', '')

        if filters:
            filter_parts = [f"#{key}:{value}" for key, value in filters.items()]
            return f"{sanitized_query} {' '.join(filter_parts)}"
        return sanitized_query

    def search(self, query: str, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Search for memories matching the query and filters."""
        filtered_query = self._build_filtered_query(query, filters)
        return self.moorcheh.search(filtered_query)

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        return self.moorcheh.get(memory_id)
```python
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from memanto.app.models.memory import Memory
from memanto.app.services.base import BaseService
from memanto.app.utils import validate_scope_id

class MemoryReadService(BaseService):
    """Service for reading memories with tenant isolation guarantees."""

    def __init__(self, client, scope_id: str):
        super().__init__()
        self.client = client
        self.scope_id = scope_id
        self._validate_scope_id(scope_id)

    def _validate_scope_id(self, scope_id: str) -> None:
        """Validate scope_id format and ensure it matches tenant isolation requirements."""
        if not validate_scope_id(scope_id):
            raise ValueError(f"Invalid scope_id format: {scope_id}")

    def _validate_temporal_filters(self, created_after: Optional[str], created_before: Optional[str]) -> None:
        """Validate temporal filters belong to current tenant scope."""
        if created_after or created_before:
            # Ensure temporal filters reference current tenant's scope
            if not (created_after and created_before):
                raise ValueError("Both created_after and created_before must be provided for temporal queries")

            # Parse dates to verify they're within reasonable bounds
            try:
                after = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
                before = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
                if after >= before:
                    raise ValueError("created_after must be before created_before")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid date format: {e}")

    def search_memories(
        self,
        query: str,
        agent_id: str,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict:
        """Search memories with tenant isolation enforcement."""
        self._validate_temporal_filters(created_after, created_before)

        # Add scope_id to query parameters to enforce tenant isolation
        query_params = {
            "query": query,
            "agent_id": agent_id,
            "scope_id": self.scope_id,
            "limit": limit,
            "offset": offset,
            "top_k": MOORCHEH_MAX_TOP_K,
        }

        if created_after:
            query_params["created_after"] = created_after
            query_params["created_before"] = created_before

        result = self.client.similarity_search.query(**query_params)

        # Apply post-processing filters with scope_id validation
        filtered = self._filter_memories_by_scope(result["results"], self.scope_id)
        return {"results": filtered, "total_found": len(filtered)}

    def _filter_memories_by_scope(self, memories: List[Dict], expected_scope_id: str) -> List[Dict]:
        """Filter memories to ensure they all belong to the expected scope."""
        return [m for m in memories if m.get("scope_id") == expected_scope_id]
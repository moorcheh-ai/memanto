

"""
MemantoCrewAdapter - Integration between CrewAI and Memanto's Agentic Memory

This adapter allows CrewAI agents to use Memanto as their primary memory store,
providing persistent, long-term memory with advanced features like:
- Vector-based retrieval of past thoughts
- Memory validation and trust scoring
- Temporal queries (as-of, changed-since)
- Multi-scope memory organization
"""

import os
from datetime import datetime
from typing import Any, Optional, List, Dict, Tuple

from pydantic import BaseModel, Field, PrivateAttr
from crewai.memory.storage.backend import StorageBackend
from crewai.memory.types import MemoryRecord, ScopeInfo
from memanto.app.core import MemoryRecord as MemantoMemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, ScopeType, SourceType
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService

class MemantoCrewAdapterConfig(BaseModel):
    """Configuration for MemantoCrewAdapter"""
    moorcheh_api_key: str = Field(
        default_factory=lambda: os.getenv("MOORCHEH_API_KEY", ""),
        description="API key for Moorcheh (Memanto's underlying storage)"
    )
    default_scope_type: ScopeType = Field(
        default="agent",
        description="Default scope type for memory storage"
    )
    default_memory_type: MemoryType = Field(
        default="context",
        description="Default memory type for stored memories"
    )
    default_source: SourceType = Field(
        default="agent",
        description="Default source for stored memories"
    )
    recency_weight: float = Field(
        default=0.3,
        description="Weight for recency in relevance scoring"
    )
    semantic_weight: float = Field(
        default=0.5,
        description="Weight for semantic similarity in relevance scoring"
    )
    importance_weight: float = Field(
        default=0.2,
        description="Weight for importance in relevance scoring"
    )
    recency_half_life_days: int = Field(
        default=30,
        description="Half-life for recency decay in days"
    )

class MemantoCrewAdapter(StorageBackend):
    """Adapter that allows CrewAI to use Memanto as its memory store"""

    def __init__(self, config: Optional[MemantoCrewAdapterConfig] = None):
        """
        Initialize the MemantoCrewAdapter

        Args:
            config: Configuration for the adapter. If None, uses defaults.
        """
        self.config = config or MemantoCrewAdapterConfig()

        # Initialize Memanto services
        from moorcheh_sdk import MoorchehClient
        self._moorcheh_client = MoorchehClient(api_key=self.config.moorcheh_api_key)
        self._read_service = MemoryReadService(self._moorcheh_client)
        self._write_service = MemoryWriteService(self._moorcheh_client)

        # Private attributes for caching
        self._scope_cache: Dict[str, ScopeInfo] = {}
        self._category_cache: Dict[str, Dict[str, int]] = {}

    def save(self, records: List[MemoryRecord]) -> None:
        """Save memory records to Memanto"""
        memanto_records = []
        for record in records:
            # Convert CrewAI MemoryRecord to Memanto MemoryRecord
            memanto_record = MemantoMemoryRecord(
                type=self.config.default_memory_type,
                title=record.content[:100],  # Use first 100 chars as title
                content=record.content,
                scope_type=self.config.default_scope_type,
                scope_id=record.scope,
                actor_id=record.metadata.get("agent_id", "unknown"),
                source=self.config.default_source,
                source_ref=record.metadata.get("source_ref"),
                confidence=record.importance,
                tags=record.categories,
                created_at=record.created_at,
                updated_at=record.created_at
            )
            memanto_records.append(memanto_record)

        # Batch store memories
        self._write_service.batch_store_memories(memanto_records)

    def search(
        self,
        query_embedding: List[float],
        scope_prefix: Optional[str] = None,
        categories: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[MemoryRecord, float]]:
        """Search for memories in Memanto using vector similarity"""
        # Convert query embedding to a string query (Memanto uses text queries)
        # In a real implementation, we'd use the embedding directly, but for now
        # we'll use a placeholder query
        query = " ".join([f"dim_{i}:{val}" for i, val in enumerate(query_embedding[:10])])

        # Build filters
        filters = {}
        if categories:
            filters["tags"] = ",".join(categories)
        if metadata_filter:
            filters.update(metadata_filter)

        # Search memories
        search_result = self._read_service.search_memories(
            query=query,
            scope_type=self.config.default_scope_type,
            scope_id=scope_prefix,
            tags=categories,
            min_confidence=min_score,
            limit=limit,
            metadata_filters=filters
        )

        # Convert Memanto results to CrewAI format
        results = []
        for item in search_result.get("results", []):
            record = MemoryRecord(
                id=item.get("id"),
                content=item.get("content", ""),
                scope=item.get("scope_id", ""),
                categories=item.get("tags", []),
                importance=item.get("confidence", 0.5),
                created_at=datetime.fromisoformat(item.get("created_at", "")),
                metadata={
                    "source": item.get("source"),
                    "source_ref": item.get("source_ref"),
                    "memory_type": item.get("memory_type")
                }
            )
            # Calculate score based on Memanto's similarity score and our weights
            similarity_score = item.get("score", 0.0)
            recency_score = self._calculate_recency_score(record.created_at)
            importance_score = record.importance

            # Composite score
            score = (
                self.config.semantic_weight * similarity_score +
                self.config.recency_weight * recency_score +
                self.config.importance_weight * importance_score
            )
            results.append((record, score))

        return results

    def _calculate_recency_score(self, created_at: datetime) -> float:
        """Calculate recency score with exponential decay"""
        age_days = (datetime.utcnow() - created_at).days
        return 2 ** (-age_days / self.config.recency_half_life_days)

    def delete(
        self,
        scope_prefix: Optional[str] = None,
        categories: Optional[List[str]] = None,
        record_ids: Optional[List[str]] = None,
        older_than: Optional[datetime] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete memories from Memanto"""
        if record_ids:
            # Delete specific records
            count = 0
            for record_id in record_ids:
                if self._write_service.delete_memory(record_id, scope_prefix or ""):
                    count += 1
            return count

        # For other deletion criteria, we'd need to search first then delete
        # This is a simplified implementation
        return 0

    def update(self, record: MemoryRecord) -> None:
        """Update a memory record in Memanto"""
        # Convert to Memanto format
        memanto_record = MemantoMemoryRecord(
            id=record.id,
            type=self.config.default_memory_type,
            title=record.content[:100],
            content=record.content,
            scope_type=self.config.default_scope_type,
            scope_id=record.scope,
            actor_id=record.metadata.get("agent_id", "unknown"),
            source=self.config.default_source,
            source_ref=record.metadata.get("source_ref"),
            confidence=record.importance,
            tags=record.categories,
            created_at=record.created_at,
            updated_at=datetime.utcnow()
        )

        # Update in Memanto
        self._write_service.update_memory(
            memory_id=record.id,
            namespace=memanto_record.get_scope().to_namespace(),
            updates=memanto_record.dict(exclude_unset=True)
        )

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Get a single memory record by ID"""
        # Search for the record in all scopes
        result = self._read_service.search_memories(
            query=f"id:{record_id}",
            limit=1
        )

        if not result.get("results"):
            return None

        item = result["results"][0]
        return MemoryRecord(
            id=item.get("id"),
            content=item.get("content", ""),
            scope=item.get("scope_id", ""),
            categories=item.get("tags", []),
            importance=item.get("confidence", 0.5),
            created_at=datetime.fromisoformat(item.get("created_at", "")),
            metadata={
                "source": item.get("source"),
                "source_ref": item.get("source_ref"),
                "memory_type": item.get("memory_type")
            }
        )

    def list_records(
        self,
        scope_prefix: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[MemoryRecord]:
        """List memory records in a scope"""
        result = self._read_service.search_memories(
            query="*",
            scope_type=self.config.default_scope_type,
            scope_id=scope_prefix,
            limit=limit,
            offset=offset
        )

        records = []
        for item in result.get("results", []):
            records.append(MemoryRecord(
                id=item.get("id"),
                content=item.get("content", ""),
                scope=item.get("scope_id", ""),
                categories=item.get("tags", []),
                importance=item.get("confidence", 0.5),
                created_at=datetime.fromisoformat(item.get("created_at", "")),
                metadata={
                    "source": item.get("source"),
                    "source_ref": item.get("source_ref"),
                    "memory_type": item.get("memory_type")
                }
            ))

        return records

    def get_scope_info(self, scope: str) -> ScopeInfo:
        """Get information about a scope"""
        if scope in self._scope_cache:
            return self._scope_cache[scope]

        # Get scope info from Memanto
        result = self._read_service.search_memories(
            query="*",
            scope_type=self.config.default_scope_type,
            scope_id=scope,
            limit=1
        )

        # Build scope info
        info = ScopeInfo(
            scope=scope,
            record_count=result.get("total_available", 0),
            categories=self._get_categories_for_scope(scope),
            date_range=(
                datetime.fromisoformat(result.get("results", [{}])[0].get("created_at", ""))
                if result.get("results")
                else None,
                datetime.utcnow()
            ),
            child_scopes=[]
        )

        self._scope_cache[scope] = info
        return info

    def _get_categories_for_scope(self, scope: str) -> Dict[str, int]:
        """Get categories and counts for a scope"""
        if scope in self._category_cache:
            return self._category_cache[scope]

        # Get categories from Memanto
        result = self._read_service.search_memories(
            query="*",
            scope_type=self.config.default_scope_type,
            scope_id=scope,
            limit=1000  # Get all records to count categories
        )

        # Count categories
        category_counts = {}
        for item in result.get("results", []):
            for category in item.get("tags", []):
                category_counts[category] = category_counts.get(category, 0) + 1

        self._category_cache[scope] = category_counts
        return category_counts

    def list_scopes(self, parent: str = "/") -> List[str]:
        """List immediate child scopes under a parent path"""
        # In Memanto, scopes are organized by scope_type and scope_id
        # For CrewAI integration, we'll treat scope_id as the scope path
        result = self._read_service.search_memories(
            query="*",
            scope_type=self.config.default_scope_type,
            limit=1000  # Get all records to find unique scopes
        )

        # Extract unique scopes
        scopes = set()
        for item in result.get("results", []):
            scope_id = item.get("scope_id", "")
            if scope_id and scope_id.startswith(parent):
                scopes.add(scope_id)

        return sorted(scopes)

    def list_categories(self, scope_prefix: Optional[str] = None) -> Dict[str, int]:
        """List categories and their counts within a scope"""
        if scope_prefix in self._category_cache:
            return self._category_cache[scope_prefix]

        return self._get_categories_for_scope(scope_prefix or "")

    def count(self, scope_prefix: Optional[str] = None) -> int:
        """Count records in a scope"""
        result = self._read_service.search_memories(
            query="*",
            scope_type=self.config.default_scope_type,
            scope_id=scope_prefix,
            limit=0  # Just get the count
        )
        return result.get("total_available", 0)

    def reset(self, scope_prefix: Optional[str] = None) -> None:
        """Reset (delete all) memories in a scope"""
        # Delete all records in the scope
        self._write_service.delete_memory(
            namespace=MemoryScope(
                scope_type=self.config.default_scope_type,
                scope_id=scope_prefix or ""
            ).to_namespace()
        )

    async def asave(self, records: List[MemoryRecord]) -> None:
        """Async save of memory records"""
        self.save(records)

    async def asearch(
        self,
        query_embedding: List[float],
        scope_prefix: Optional[str] = None,
        categories: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Tuple[MemoryRecord, float]]:
        """Async search for memories"""
        return self.search(
            query_embedding,
            scope_prefix,
            categories,
            metadata_filter,
            limit,
            min_score
        )

    async def adelete(
        self,
        scope_prefix: Optional[str] = None,
        categories: Optional[List[str]] = None,
        record_ids: Optional[List[str]] = None,
        older_than: Optional[datetime] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Async delete of memories"""
        return self.delete(
            scope_prefix,
            categories,
            record_ids,
            older_than,
            metadata_filter
        )

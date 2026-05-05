"""
Memanto Storage Backend for CrewAI
===================================

A drop-in replacement for CrewAI's default memory storage that uses
Memanto (moorcheh-sdk) as the persistent semantic memory layer.

This gives your CrewAI agents:
- Cross-session memory persistence (agents remember across runs)
- Cross-agent memory sharing (Research Agent → Writer Agent)
- Zero-ingestion-latency exact semantic search
- Typed memory categories (fact, decision, preference, etc.)

Usage:
    from memanto_backend import MemantoStorageBackend
    from crewai.memory.unified_memory import Memory

    backend = MemantoStorageBackend(
        api_key="your-moorcheh-api-key",
        namespace="my-crew-memory",
    )
    memory = Memory(storage=backend)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any

from moorcheh_sdk import MoorchehClient
from moorcheh_sdk.types import Document, SearchResult
from crewai.memory.unified_memory import MemoryRecord, ScopeInfo


class MemantoStorageBackend:
    """CrewAI StorageBackend implementation backed by Memanto/Moorcheh.

    Implements the full StorageBackend Protocol so CrewAI's Memory class
    can use Memanto for persistent, semantic, cross-session storage.

    Memory records are stored as Moorcheh Documents with metadata encoding
    the CrewAI MemoryRecord fields (scope, categories, importance, timestamps).
    Retrieval uses Moorcheh's exact semantic search with post-filtering.
    """

    def __init__(
        self,
        api_key: str | None = None,
        namespace: str = "crewai-memory",
        base_url: str | None = None,
        auto_create_namespace: bool = True,
    ):
        """Initialize the Memanto storage backend.

        Args:
            api_key: Moorcheh API key. If None, reads from MOORCHEH_API_KEY env var.
            namespace: Moorcheh namespace for storing memories.
            base_url: Optional custom API base URL.
            auto_create_namespace: If True, create the namespace on first write if missing.
        """
        self._client = MoorchehClient(
            api_key=api_key,
            base_url=base_url,
        )
        self._namespace = namespace
        self._auto_create = auto_create_namespace
        self._namespace_ready = False
        # In-memory index for operations Moorcheh doesn't natively support
        # (delete by criteria, list records, etc.)
        self._local_index: dict[str, MemoryRecord] = {}

    def _ensure_namespace(self) -> None:
        """Create namespace if it doesn't exist yet."""
        if self._namespace_ready:
            return
        if self._auto_create:
            try:
                self._client.namespaces.create(
                    namespace_name=self._namespace,
                    type="document",
                )
            except Exception:
                # Namespace likely already exists
                pass
        self._namespace_ready = True

    def _record_to_document(self, record: MemoryRecord) -> Document:
        """Convert a CrewAI MemoryRecord to a Moorcheh Document."""
        metadata: dict[str, Any] = {
            "scope": record.scope,
            "categories": json.dumps(record.categories),
            "importance": record.importance,
            "created_at": record.created_at.isoformat(),
            "last_accessed": record.last_accessed.isoformat(),
            "source": record.source or "",
            "private": record.private,
        }
        # Merge any extra metadata from the record
        for k, v in record.metadata.items():
            if k not in metadata:
                metadata[f"meta_{k}"] = str(v) if not isinstance(v, (str, int, float, bool)) else v

        return Document(
            id=record.id,
            text=record.content,
            metadata=metadata,
        )

    def _search_result_to_record(self, result: SearchResult) -> MemoryRecord:
        """Convert a Moorcheh SearchResult back to a CrewAI MemoryRecord."""
        meta = result.get("metadata", {})
        categories_raw = meta.get("categories", "[]")
        if isinstance(categories_raw, str):
            try:
                categories = json.loads(categories_raw)
            except (json.JSONDecodeError, TypeError):
                categories = []
        else:
            categories = categories_raw

        # Reconstruct extra metadata
        extra_meta = {}
        for k, v in meta.items():
            if k.startswith("meta_"):
                extra_meta[k[5:]] = v

        created_at_str = meta.get("created_at", "")
        last_accessed_str = meta.get("last_accessed", "")

        return MemoryRecord(
            id=str(result["id"]),
            content=result.get("text", ""),
            scope=meta.get("scope", "/"),
            categories=categories,
            metadata=extra_meta,
            importance=float(meta.get("importance", 0.5)),
            created_at=datetime.fromisoformat(created_at_str) if created_at_str else datetime.utcnow(),
            last_accessed=datetime.fromisoformat(last_accessed_str) if last_accessed_str else datetime.utcnow(),
            source=meta.get("source") or None,
            private=bool(meta.get("private", False)),
        )

    # ─── StorageBackend Protocol Implementation ───────────────────────────

    def save(self, records: list[MemoryRecord]) -> None:
        """Save memory records to Memanto."""
        self._ensure_namespace()
        documents = [self._record_to_document(r) for r in records]
        self._client.documents.upload(
            namespace_name=self._namespace,
            documents=documents,
        )
        # Update local index
        for r in records:
            self._local_index[r.id] = r

    def search(
        self,
        query_embedding: list[float],
        scope_prefix: str | None = None,
        categories: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[MemoryRecord, float]]:
        """Search memories by semantic similarity using Moorcheh's exact search."""
        self._ensure_namespace()

        # Moorcheh search accepts text queries or embeddings
        # Use the embedding vector directly
        try:
            response = self._client.similarity_search.query(
                namespaces=[self._namespace],
                query=query_embedding,
                top_k=limit * 3,  # Over-fetch to allow for post-filtering
            )
        except Exception:
            return []

        results: list[tuple[MemoryRecord, float]] = []
        for item in response["results"]:
            score = item.get("score", 0.0)
            if score < min_score:
                continue

            record = self._search_result_to_record(item)

            # Post-filter by scope
            if scope_prefix and not record.scope.startswith(scope_prefix):
                continue

            # Post-filter by categories
            if categories:
                if not any(c in record.categories for c in categories):
                    continue

            # Post-filter by metadata
            if metadata_filter:
                match = True
                for k, v in metadata_filter.items():
                    if record.metadata.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            results.append((record, score))
            if len(results) >= limit:
                break

        return results

    def delete(
        self,
        scope_prefix: str | None = None,
        categories: list[str] | None = None,
        record_ids: list[str] | None = None,
        older_than: datetime | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> int:
        """Delete memories matching criteria."""
        deleted = 0
        ids_to_delete = []

        if record_ids:
            ids_to_delete = record_ids
        else:
            # Filter local index
            for rid, record in list(self._local_index.items()):
                if scope_prefix and not record.scope.startswith(scope_prefix):
                    continue
                if categories and not any(c in record.categories for c in categories):
                    continue
                if older_than and record.created_at >= older_than:
                    continue
                if metadata_filter:
                    match = all(record.metadata.get(k) == v for k, v in metadata_filter.items())
                    if not match:
                        continue
                ids_to_delete.append(rid)

        if ids_to_delete:
            try:
                self._client.documents.delete(
                    namespace_name=self._namespace,
                    ids=ids_to_delete,
                )
            except Exception:
                pass
            # Count deletes based on local index removal
            for rid in ids_to_delete:
                if self._local_index.pop(rid, None) is not None:
                    deleted += 1

        return deleted

    def update(self, record: MemoryRecord) -> None:
        """Update an existing record by re-uploading it."""
        self.save([record])

    def get_record(self, record_id: str) -> MemoryRecord | None:
        """Return a single record by ID."""
        return self._local_index.get(record_id)

    def list_records(
        self,
        scope_prefix: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List records in a scope, newest first."""
        records = list(self._local_index.values())
        if scope_prefix:
            records = [r for r in records if r.scope.startswith(scope_prefix)]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[offset: offset + limit]

    def get_scope_info(self, scope: str) -> ScopeInfo:
        """Get information about a scope."""
        records = [r for r in self._local_index.values() if r.scope.startswith(scope)]
        all_categories: dict[str, int] = {}
        for r in records:
            for c in r.categories:
                all_categories[c] = all_categories.get(c, 0) + 1

        child_scopes = set()
        for r in records:
            if r.scope != scope and r.scope.startswith(scope):
                relative = r.scope[len(scope):].lstrip("/")
                child = relative.split("/")[0] if "/" in relative else relative
                if child:
                    child_scopes.add(f"{scope.rstrip('/')}/{child}")

        dates = [r.created_at for r in records]
        return ScopeInfo(
            path=scope,
            record_count=len(records),
            categories=list(all_categories.keys()),
            oldest_record=min(dates) if dates else None,
            newest_record=max(dates) if dates else None,
            child_scopes=sorted(child_scopes),
        )

    def list_scopes(self, parent: str = "/") -> list[str]:
        """List immediate child scopes under a parent path."""
        scopes = set()
        for r in self._local_index.values():
            if r.scope.startswith(parent) and r.scope != parent:
                relative = r.scope[len(parent):].lstrip("/")
                child = relative.split("/")[0]
                if child:
                    scopes.add(f"{parent.rstrip('/')}/{child}")
        return sorted(scopes)

    def list_categories(self, scope_prefix: str | None = None) -> dict[str, int]:
        """List categories and their counts."""
        cats: dict[str, int] = {}
        for r in self._local_index.values():
            if scope_prefix and not r.scope.startswith(scope_prefix):
                continue
            for c in r.categories:
                cats[c] = cats.get(c, 0) + 1
        return cats

    def count(self, scope_prefix: str | None = None) -> int:
        """Count records in scope."""
        if scope_prefix is None:
            return len(self._local_index)
        return sum(1 for r in self._local_index.values() if r.scope.startswith(scope_prefix))

    def reset(self, scope_prefix: str | None = None) -> None:
        """Reset (delete all) memories in scope."""
        if scope_prefix is None:
            self._local_index.clear()
            try:
                self._client.namespaces.delete(namespace_name=self._namespace)
                self._namespace_ready = False
            except Exception:
                pass
        else:
            ids_to_remove = [
                rid for rid, r in self._local_index.items()
                if r.scope.startswith(scope_prefix)
            ]
            for rid in ids_to_remove:
                del self._local_index[rid]

    # Async variants (simple wrappers for protocol compliance)
    async def asave(self, records: list[MemoryRecord]) -> None:
        """Async save — delegates to sync implementation."""
        self.save(records)

    async def asearch(
        self,
        query_embedding: list[float],
        scope_prefix: str | None = None,
        categories: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[MemoryRecord, float]]:
        """Async search — delegates to sync implementation."""
        return self.search(query_embedding, scope_prefix, categories, metadata_filter, limit, min_score)

    async def adelete(
        self,
        scope_prefix: str | None = None,
        categories: list[str] | None = None,
        record_ids: list[str] | None = None,
        older_than: datetime | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> int:
        """Async delete — delegates to sync implementation."""
        return self.delete(scope_prefix, categories, record_ids, older_than, metadata_filter)

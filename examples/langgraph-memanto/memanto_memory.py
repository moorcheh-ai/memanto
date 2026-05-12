"""
Memanto memory adapter — wraps Memanto's core models for LangGraph integration.
Provides store/retrieve/search operations for cross-session memory.
"""

import os
import uuid
from datetime import datetime
from typing import Any

from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, SourceType


class MemantoMemory:
    """Adapter for storing and retrieving memories via Memanto/Moorcheh."""

    def __init__(self, api_key: str | None = None, base_url: str = "http://localhost:8000"):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.base_url = base_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from moorcheh_sdk import MoorchehClient
            self._client = MoorchehClient(api_key=self.api_key)
        return self._client

    def store_memory(
        self,
        memory_type: MemoryType,
        title: str,
        content: str,
        scope_type: str = "user",
        scope_id: str = "default",
        actor_id: str = "agent",
        source: SourceType = "agent",
        tags: list[str] | None = None,
        confidence: float = 0.8,
    ) -> MemoryRecord:
        record = MemoryRecord(
            type=memory_type,
            title=title,
            content=content,
            scope_type=scope_type,
            scope_id=scope_id,
            actor_id=actor_id,
            source=source,
            tags=tags or [],
            confidence=confidence,
        )
        scope = MemoryScope(scope_type=scope_type, scope_id=scope_id)
        namespace = scope.to_namespace()
        doc = record.to_moorcheh_document()
        self.client.upsert(collection=namespace, documents=[doc])
        return record

    def search_memories(
        self,
        query: str,
        scope_type: str = "user",
        scope_id: str = "default",
        memory_type: MemoryType | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        namespace = MemoryScope(scope_type=scope_type, scope_id=scope_id).to_namespace()
        filter_expr = f"#status:active"
        if memory_type:
            filter_expr += f" #memory_type:{memory_type}"
        results = self.client.search(
            collection=namespace,
            query=query,
            limit=limit,
            filter=filter_expr,
        )
        return results

    def get_recent_memories(
        self,
        scope_type: str = "user",
        scope_id: str = "default",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        namespace = MemoryScope(scope_type=scope_type, scope_id=scope_id).to_namespace()
        results = self.client.search(
            collection=namespace,
            query="",
            limit=limit,
            filter="#status:active",
        )
        return results

    def get_cross_session_context(self, user_id: str) -> str:
        """Retrieve memories from previous sessions to provide cross-session context."""
        memories = self.get_recent_memories(scope_type="user", scope_id=user_id, limit=15)
        if not memories:
            return ""

        lines = []
        for m in memories:
            mtype = m.get("memory_type", "unknown")
            text = m.get("text", "")
            lines.append(f"[{mtype}] {text}")
        return "\n".join(lines)

"""Small Memanto adapter used by the LangGraph example.

The adapter keeps the example runnable in two modes:

1. With MOORCHEH_API_KEY, it uses the repository's SdkClient and writes to
   Memanto.
2. Without a key, it uses an in-memory fallback so reviewers can run the
   LangGraph flow locally before configuring credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class MemoryRecord:
    memory_type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    source: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory_id": f"dry-run-{uuid4().hex[:10]}",
            "type": self.memory_type,
            "title": self.title,
            "content": self.content,
            "confidence": self.confidence,
            "tags": self.tags,
            "source": self.source,
            "created_at": self.created_at,
        }


class InMemoryMemantoStore:
    """Deterministic local fallback for running the example without API keys."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
        source: str = "langgraph-demo",
    ) -> dict[str, Any]:
        record = MemoryRecord(
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source=source,
        )
        self._records.append(record)
        return {"status": "stored", **record.as_dict()}

    def recall(self, query: str, limit: int = 5) -> dict[str, Any]:
        query_terms = {
            token.strip(".,?!:;()[]{}").lower()
            for token in query.split()
            if len(token.strip(".,?!:;()[]{}")) > 2
        }

        def score(record: MemoryRecord) -> int:
            haystack = f"{record.title} {record.content} {' '.join(record.tags)}".lower()
            return sum(1 for term in query_terms if term in haystack)

        ranked = sorted(self._records, key=score, reverse=True)
        memories = [record.as_dict() for record in ranked[:limit] if score(record) > 0]
        if not memories:
            memories = [record.as_dict() for record in self._records[-limit:]]

        return {"memories": memories, "count": len(memories), "query": query}


class MemantoMemory:
    """Thin wrapper around Memanto's SDK client with a dry-run fallback."""

    def __init__(
        self,
        agent_id: str,
        api_key: str | None = None,
        dry_run: bool = False,
        store: InMemoryMemantoStore | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.api_key = api_key
        self.dry_run = dry_run or not api_key
        self._store = store or InMemoryMemantoStore()
        self._client: Any | None = None

        if not self.dry_run:
            from memanto.cli.client.sdk_client import SdkClient

            self._client = SdkClient(api_key=api_key or "")
            self._ensure_agent()

    def _ensure_agent(self) -> None:
        if self._client is None:
            return

        try:
            self._client.create_agent(
                self.agent_id,
                pattern="tool",
                description="LangGraph support agent with persistent Memanto memory",
            )
        except Exception:
            # Existing agents are fine for repeatable demos.
            pass
        self._client.activate_agent(self.agent_id)

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.dry_run:
            return self._store.remember(
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tags,
            )

        return self._client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source="langgraph-demo",
            provenance="explicit_statement",
        )

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if self.dry_run:
            return self._store.recall(query=query, limit=limit)["memories"]

        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
        )
        return result.get("memories", [])

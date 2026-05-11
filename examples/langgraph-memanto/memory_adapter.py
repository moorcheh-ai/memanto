"""Memory adapters used by the LangGraph + Memanto example."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


@dataclass(slots=True)
class MemoryRecord:
    """Small normalized shape consumed by the example graph."""

    title: str
    content: str
    memory_type: str = "preference"
    confidence: float = 0.9
    tags: list[str] = field(default_factory=list)
    memory_id: str = field(default_factory=lambda: f"dry-{uuid4().hex[:10]}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "title": self.title,
            "content": self.content,
            "type": self.memory_type,
            "confidence": self.confidence,
            "tags": self.tags,
        }


class MemoryStore(Protocol):
    """Protocol shared by the real Memanto adapter and local dry-run store."""

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str = "preference",
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist one memory and return a result dictionary."""

    def recall(
        self,
        *,
        query: str,
        limit: int = 4,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return matching memories for a natural-language query."""


class InMemoryMemantoStore:
    """
    Memanto-shaped dry-run store.

    It keeps memories outside LangGraph state so the example can prove the graph
    boundary locally without requiring reviewer API keys.
    """

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str = "preference",
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        record = MemoryRecord(
            title=title,
            content=content,
            memory_type=memory_type,
            confidence=confidence,
            tags=tags or [],
        )
        self._records.append(record)
        return record.as_dict()

    def recall(
        self,
        *,
        query: str,
        limit: int = 4,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        terms = _tokenize(query)
        allowed_types = set(memory_types or [])
        scored: list[tuple[int, MemoryRecord]] = []

        for record in self._records:
            if allowed_types and record.memory_type not in allowed_types:
                continue

            searchable = " ".join([record.title, record.content, " ".join(record.tags)])
            score = len(terms.intersection(_tokenize(searchable)))
            if score:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [record.as_dict() for _, record in scored[:limit]]


class SdkMemantoStore:
    """Adapter around Memanto's SDK client."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        duration_hours: int = 6,
    ) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self._ensure_agent_exists()
        self.client.activate_agent(agent_id, duration_hours=duration_hours)

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str = "preference",
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-example",
            provenance="explicit_statement",
        )

    def recall(
        self,
        *,
        query: str,
        limit: int = 4,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return list(result.get("memories", []))

    def close(self) -> None:
        self.client.deactivate_agent(self.agent_id)

    def _ensure_agent_exists(self) -> None:
        existing = {agent["agent_id"] for agent in self.client.list_agents()}
        if self.agent_id in existing:
            return

        self.client.create_agent(
            agent_id=self.agent_id,
            pattern="support",
            description="LangGraph support agent with Memanto long-term memory",
        )


def _tokenize(value: str) -> set[str]:
    return {
        token.strip(".,!?;:()[]{}\"'").lower()
        for token in value.split()
        if len(token.strip(".,!?;:()[]{}\"'")) > 2
    }

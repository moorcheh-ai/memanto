"""Memory backends used by the LangGraph + Memanto example."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Memory:
    """Small normalized memory record used by the example graph."""

    memory_id: str
    memory_type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    source_session: str


class MemoryBackend(Protocol):
    """Backend contract shared by the local and Memanto SDK stores."""

    def remember(self, memory: Memory) -> str:
        """Persist one memory and return its ID."""

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        """Return memories relevant to the query."""


class LocalJsonMemoryBackend:
    """Reviewer-friendly local backend with deterministic keyword recall."""

    def __init__(self, path: Path) -> None:
        """Configure a local JSON store."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: Memory) -> str:
        """Persist one memory unless its ID already exists."""
        memories = self._load()
        if any(existing.memory_id == memory.memory_id for existing in memories):
            return memory.memory_id
        memories.append(memory)
        self._save(memories)
        return memory.memory_id

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        """Return keyword-ranked memories relevant to the query."""
        memories = self._load()
        query_terms = _terms(query)

        def score(memory: Memory) -> tuple[int, float]:
            """Rank one memory by keyword overlap and confidence."""
            haystack = " ".join(
                [memory.title, memory.content, memory.memory_type, *memory.tags]
            )
            overlap = len(query_terms & _terms(haystack))
            tag_bonus = len(query_terms & set(memory.tags))
            return (overlap + tag_bonus, memory.confidence)

        ranked = sorted(memories, key=score, reverse=True)
        return [memory for memory in ranked if score(memory)[0] > 0][:limit]

    def reset(self) -> None:
        """Clear all locally persisted memories."""
        self.path.write_text("[]\n", encoding="utf-8")

    def _load(self) -> list[Memory]:
        """Load locally persisted memories from disk."""
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Memory(**item) for item in raw]

    def _save(self, memories: list[Memory]) -> None:
        """Write memories to the local JSON store."""
        payload = [asdict(memory) for memory in memories]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class MemantoSdkMemoryBackend:
    """Live backend that stores memories in Memanto via ``SdkClient``."""

    def __init__(self, agent_id: str, api_key: str | None = None) -> None:
        """Create or reactivate the SDK-backed demo agent."""
        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        resolved_key = api_key or os.environ.get("MOORCHEH_API_KEY")
        if not resolved_key:
            raise ValueError("MOORCHEH_API_KEY is required for the Memanto backend")

        self.agent_id = agent_id
        self.client = SdkClient(api_key=resolved_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description="LangGraph support agent with durable Memanto memory",
            )
        except AgentAlreadyExistsError:
            pass
        self.client.activate_agent(agent_id, duration_hours=6)

    def remember(self, memory: Memory) -> str:
        """Store one memory through the Memanto SDK."""
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        """Normalize SDK recall results into example memory records."""
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
        )
        memories = []
        for item in result.get("memories", []):
            memories.append(
                Memory(
                    memory_id=str(item.get("id") or item.get("memory_id") or uuid.uuid4()),
                    memory_type=str(item.get("type", "fact")),
                    title=str(item.get("title", "Untitled")),
                    content=str(item.get("content", "")),
                    confidence=float(item.get("confidence", 0.8)),
                    tags=list(item.get("tags", [])),
                    source_session=str(item.get("source_session", "memanto")),
                )
            )
        return memories


def _terms(text: str) -> set[str]:
    """Extract normalized keyword terms for local recall."""
    return {
        term
        for term in re.findall(r"[a-z0-9][a-z0-9_-]+", text.lower())
        if len(term) > 2
    }


def stable_memory_id(source_session: str, title: str) -> str:
    """Create an idempotent memory ID for repeatable local demos."""

    raw = f"{source_session}:{title}".encode()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw.hex()))


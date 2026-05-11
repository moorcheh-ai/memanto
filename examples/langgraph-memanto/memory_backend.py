"""
Memory backends for the LangGraph + Memanto example.

The production path uses Memanto's SdkClient. A tiny JSON backend is included
only so contributors can smoke-test the LangGraph wiring without a Moorcheh key.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MemoryItem:
    """A memory returned to the graph."""

    title: str
    content: str
    memory_type: str
    confidence: float
    tags: list[str]


class MemoryBackend(Protocol):
    """Backend contract used by the LangGraph nodes."""

    def setup(self) -> None:
        """Prepare the backend for memory operations."""

    def close(self) -> None:
        """Release the backend session."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        """Store one memory and return its identifier."""

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryItem]:
        """Recall memories relevant to a query."""

    def wait_until_indexed(
        self,
        *,
        query: str,
        minimum_count: int,
        timeout_seconds: float = 45.0,
        poll_interval_seconds: float = 2.0,
    ) -> list[MemoryItem]:
        """Wait until recently written memories are queryable."""


class MemantoMemoryBackend:
    """Memanto-backed implementation used by the bounty example."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph customer support demo with persistent memory",
    ) -> None:
        self.agent_id = agent_id
        self.description = description
        from memanto.cli.client.sdk_client import SdkClient

        self.client = SdkClient(api_key=api_key)
        self._active = False

    def setup(self) -> None:
        from memanto.app.utils.errors import AgentAlreadyExistsError

        try:
            self.client.create_agent(
                self.agent_id,
                pattern="support",
                description=self.description,
            )
        except AgentAlreadyExistsError:
            pass

        self.client.activate_agent(self.agent_id, duration_hours=6)
        self._active = True

    def close(self) -> None:
        if not self._active:
            return
        self.client.deactivate_agent(self.agent_id)
        self._active = False

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-example",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryItem]:
        raw_items: list[dict[str, Any]]
        if memory_types and len(memory_types) > 1:
            raw_items = []
            seen_ids: set[str] = set()

            for memory_type in memory_types:
                result = self.client.recall(
                    agent_id=self.agent_id,
                    query=query,
                    limit=limit,
                    type=[memory_type],
                )
                for item in result.get("memories", []):
                    item_id = str(item.get("id", ""))
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    raw_items.append(item)

            raw_items.sort(
                key=lambda item: float(item.get("score", 0.0) or 0.0),
                reverse=True,
            )
            raw_items = raw_items[:limit]
        else:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
                type=memory_types,
            )
            raw_items = result.get("memories", [])

        memories: list[MemoryItem] = []
        for item in raw_items:
            raw_tags: Any = item.get("tags", []) or []
            memories.append(
                MemoryItem(
                    title=str(item.get("title", "Untitled")),
                    content=str(item.get("content", "")),
                    memory_type=str(item.get("type", "fact")),
                    confidence=float(item.get("confidence", 0.0) or 0.0),
                    tags=[str(tag) for tag in raw_tags],
                )
            )
        return memories

    def wait_until_indexed(
        self,
        *,
        query: str,
        minimum_count: int,
        timeout_seconds: float = 45.0,
        poll_interval_seconds: float = 2.0,
    ) -> list[MemoryItem]:
        deadline = time.monotonic() + timeout_seconds
        latest: list[MemoryItem] = []

        while time.monotonic() < deadline:
            latest = self.recall(query=query, limit=max(5, minimum_count))
            if len(latest) >= minimum_count:
                return latest
            time.sleep(poll_interval_seconds)

        return latest


class LocalJsonMemoryBackend:
    """
    Minimal offline backend for graph smoke tests.

    This is deliberately not the bounty backend; it mirrors the same contract so
    the LangGraph example can be run without network credentials.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._memories: list[MemoryItem] = []

    def setup(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._memories = [MemoryItem(**item) for item in raw]

    def close(self) -> None:
        self.path.write_text(
            json.dumps([asdict(item) for item in self._memories], indent=2),
            encoding="utf-8",
        )

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        item = MemoryItem(
            title=title,
            content=content,
            memory_type=memory_type,
            confidence=confidence,
            tags=tags or [],
        )
        self._memories.append(item)
        return f"local-{len(self._memories)}"

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryItem]:
        query_terms = {term.lower().strip(".,!?") for term in query.split()}
        scored: list[tuple[int, MemoryItem]] = []

        for item in self._memories:
            if memory_types and item.memory_type not in memory_types:
                continue

            haystack = f"{item.title} {item.content} {' '.join(item.tags)}".lower()
            score = sum(1 for term in query_terms if term and term in haystack)
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for score, item in scored if score > 0][:limit]

    def wait_until_indexed(
        self,
        *,
        query: str,
        minimum_count: int,
        timeout_seconds: float = 45.0,
        poll_interval_seconds: float = 2.0,
    ) -> list[MemoryItem]:
        return self.recall(query=query, limit=max(5, minimum_count))

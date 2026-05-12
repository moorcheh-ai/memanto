from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


@dataclass
class MemoryItem:
    id: str
    agent_id: str
    type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    created_at: str
    score: float = 1.0


class MemoryBackend(Protocol):
    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> MemoryItem:
        ...

    def recall(self, *, agent_id: str, query: str, limit: int = 5) -> list[MemoryItem]:
        ...


class LocalJsonMemoryBackend:
    """Small local backend for demos, recordings, and CI without API keys."""

    def __init__(self, path: str | Path = ".langgraph_memanto_memory.json") -> None:
        self.path = Path(path)

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            id=f"local-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        records = self._load()
        records.append(asdict(item))
        self._save(records)
        return item

    def recall(self, *, agent_id: str, query: str, limit: int = 5) -> list[MemoryItem]:
        query_terms = _terms(query)
        scored: list[MemoryItem] = []

        for record in self._load():
            if record.get("agent_id") != agent_id:
                continue

            haystack = " ".join(
                [
                    str(record.get("title", "")),
                    str(record.get("content", "")),
                    " ".join(record.get("tags", [])),
                    str(record.get("type", "")),
                ]
            )
            overlap = len(query_terms & _terms(haystack))
            if overlap == 0:
                continue

            item = MemoryItem(**record)
            item.score = overlap / max(len(query_terms), 1)
            scored.append(item)

        scored.sort(key=lambda item: (item.score, item.created_at), reverse=True)
        return scored[:limit]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(records, indent=2), encoding="utf-8")


class MemantoMemoryBackend:
    """Memanto-backed implementation using this repository's DirectClient."""

    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise ValueError("MOORCHEH_API_KEY is required for the memanto backend")

        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.direct_client import DirectClient

        self._agent_exists_error = AgentAlreadyExistsError
        self.client = DirectClient(api_key)
        self._active_agent_id: str | None = None

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> MemoryItem:
        self._ensure_session(agent_id)
        result = self.client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )
        return MemoryItem(
            id=str(result["memory_id"]),
            agent_id=agent_id,
            type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def recall(self, *, agent_id: str, query: str, limit: int = 5) -> list[MemoryItem]:
        self._ensure_session(agent_id)
        result = self.client.recall(agent_id=agent_id, query=query, limit=limit)
        memories: list[MemoryItem] = []
        for raw in result.get("memories", []):
            metadata = raw.get("metadata") or {}
            memories.append(
                MemoryItem(
                    id=str(raw.get("id") or metadata.get("memory_id") or "memanto"),
                    agent_id=agent_id,
                    type=str(metadata.get("memory_type") or raw.get("type") or "fact"),
                    title=str(metadata.get("title") or raw.get("title") or "Memory"),
                    content=str(raw.get("content") or raw.get("text") or raw),
                    confidence=float(metadata.get("confidence") or 0.8),
                    tags=list(metadata.get("tags") or []),
                    created_at=str(
                        metadata.get("created_at")
                        or datetime.now(timezone.utc).isoformat()
                    ),
                    score=float(raw.get("score") or raw.get("similarity") or 1.0),
                )
            )
        return memories

    def _ensure_session(self, agent_id: str) -> None:
        if self._active_agent_id == agent_id:
            return

        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description="LangGraph support agent with Memanto memory",
            )
        except self._agent_exists_error:
            pass

        self.client.activate_agent(agent_id)
        self._active_agent_id = agent_id


def create_memory_backend(name: str, local_path: str | Path | None = None) -> MemoryBackend:
    if name == "local":
        return LocalJsonMemoryBackend(local_path or ".langgraph_memanto_memory.json")
    if name == "memanto":
        return MemantoMemoryBackend()
    raise ValueError("backend must be either 'local' or 'memanto'")


def _terms(value: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return {part for part in cleaned.split() if len(part) > 2}

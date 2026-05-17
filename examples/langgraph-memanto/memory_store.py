"""
Memory backends for the LangGraph + Memanto example.

The production backend uses Memanto's SdkClient. The local backend keeps the
example reviewable without API secrets while preserving the same remember/recall
contract used by the graph.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "new",
    "no",
    "of",
    "on",
    "or",
    "our",
    "prepare",
    "state",
    "the",
    "this",
    "thread",
    "to",
    "today",
    "with",
}


@dataclass
class Memory:
    memory_type: str
    title: str
    content: str
    confidence: float = 0.9
    tags: list[str] = field(default_factory=list)
    source: str = "langgraph-agent"
    memory_id: str | None = None
    created_at: str | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("memory_type")
        return payload


class MemoryStore(Protocol):
    def setup(self) -> None:
        """Prepare the backend for memory operations."""

    def remember(self, memory: Memory) -> Memory:
        """Persist one memory and return the stored record."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[Memory]:
        """Retrieve memories relevant to the query."""

    def close(self) -> None:
        """Release any active resources or sessions."""


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())
        if token not in STOPWORDS and len(token) > 1
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalJsonMemoryStore:
    """Tiny deterministic backend for demos, tests, and PR review."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def setup(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def remember(self, memory: Memory) -> Memory:
        records = self._load()
        stored = Memory(
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=list(memory.tags),
            source=memory.source,
            memory_id=memory.memory_id or f"local-{uuid.uuid4().hex[:10]}",
            created_at=memory.created_at or _now_iso(),
        )
        records.append(stored.to_dict())
        self._save(records)
        return stored

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[Memory]:
        query_tokens = _tokens(query)
        scored: list[Memory] = []

        for raw in self._load():
            memory = _memory_from_mapping(raw)
            if memory_types and memory.memory_type not in memory_types:
                continue

            haystack = " ".join([memory.title, memory.content, " ".join(memory.tags)])
            memory_tokens = _tokens(haystack)
            overlap = len(query_tokens & memory_tokens)
            exact_bonus = 2 if query.lower() in haystack.lower() else 0
            tag_bonus = len(query_tokens & set(memory.tags))
            score = overlap + exact_bonus + tag_bonus

            if score:
                memory.score = float(score)
                scored.append(memory)

        scored.sort(
            key=lambda item: (
                item.score or 0,
                item.confidence,
                item.created_at or "",
            ),
            reverse=True,
        )
        return scored[:limit]

    def close(self) -> None:
        return None

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.path.write_text(
            json.dumps(records, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class MemantoSdkMemoryStore:
    """Memanto-backed durable memory for the live demo path."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        duration_hours: int = 6,
    ) -> None:
        self.api_key = api_key
        self.agent_id = agent_id
        self.duration_hours = duration_hours
        self._client: Any | None = None

    def setup(self) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self._client = SdkClient(api_key=self.api_key)
        try:
            self._client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description="LangGraph recruiting assistant memory example",
            )
        except Exception:
            # The demo is repeatable; an existing agent is expected after run one.
            pass
        self._client.activate_agent(self.agent_id, duration_hours=self.duration_hours)

    def remember(self, memory: Memory) -> Memory:
        client = self._require_client()
        result = client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
            provenance="explicit_statement",
        )
        stored = Memory(
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
            memory_id=result.get("memory_id"),
            created_at=_now_iso(),
        )
        return stored

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[Memory]:
        client = self._require_client()
        result = client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return [_memory_from_mapping(raw) for raw in result.get("memories", [])]

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.deactivate_agent(self.agent_id)
            except Exception:
                pass

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Call setup() before using MemantoSdkMemoryStore")
        return self._client


def build_memory_store(
    backend: str,
    *,
    agent_id: str,
    local_path: str | Path,
) -> MemoryStore:
    if backend == "local":
        return LocalJsonMemoryStore(local_path)
    if backend == "memanto":
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key.strip():
            raise RuntimeError(
                "MOORCHEH_API_KEY is required for --backend memanto. "
                "Use --backend local for a credential-free demo."
            )
        return MemantoSdkMemoryStore(api_key=api_key, agent_id=agent_id)
    raise ValueError(f"Unsupported backend: {backend}")


def _memory_from_mapping(raw: dict[str, Any]) -> Memory:
    metadata = raw.get("metadata") or {}
    tags = raw.get("tags") or metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

    content = raw.get("content") or raw.get("text") or metadata.get("content") or ""
    title = raw.get("title") or metadata.get("title") or _title_from_content(content)
    memory_type = (
        raw.get("type")
        or raw.get("memory_type")
        or metadata.get("memory_type")
        or "fact"
    )

    return Memory(
        memory_type=str(memory_type),
        title=str(title),
        content=str(content),
        confidence=float(raw.get("confidence") or metadata.get("confidence") or 0.8),
        tags=list(tags),
        source=str(raw.get("source") or metadata.get("source") or "memanto"),
        memory_id=raw.get("memory_id") or raw.get("id"),
        created_at=raw.get("created_at") or metadata.get("created_at"),
        score=raw.get("score") or raw.get("similarity"),
    )


def _title_from_content(content: str) -> str:
    first_line = content.strip().splitlines()[0] if content.strip() else "Memory"
    return first_line[:97] + "..." if len(first_line) > 100 else first_line

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import httpx


@dataclass
class Memory:
    title: str
    content: str
    type: str = "fact"
    confidence: float = 0.95
    tags: list[str] | None = None


class MemoryAdapter(Protocol):
    def remember(self, memory: Memory) -> None: ...

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]: ...


class MemantoHttpMemory:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        agent_id: str | None = None,
        session_token: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ["MEMANTO_BASE_URL"]).rstrip("/")
        self.agent_id = agent_id or os.environ["MEMANTO_AGENT_ID"]
        self.session_token = session_token or os.environ["MEMANTO_SESSION_TOKEN"]

    def remember(self, memory: Memory) -> None:
        response = httpx.post(
            f"{self.base_url}/api/v2/agents/{self.agent_id}/remember",
            headers={"X-Session-Token": self.session_token},
            json={
                "title": memory.title,
                "content": memory.content,
                "type": memory.type,
                "confidence": memory.confidence,
                "tags": memory.tags or [],
                "source": "langgraph-memanto-example",
                "provenance": "explicit_statement",
            },
            timeout=30,
        )
        response.raise_for_status()

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        response = httpx.post(
            f"{self.base_url}/api/v2/agents/{self.agent_id}/recall",
            headers={"X-Session-Token": self.session_token},
            json={"query": query, "limit": limit},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        raw_items = payload.get("results") or payload.get("memories") or []
        return [
            Memory(
                title=item.get("title") or "Memory",
                content=item.get("content") or item.get("text") or str(item),
                type=item.get("type") or "fact",
                confidence=float(item.get("confidence") or 0.0),
                tags=item.get("tags") or [],
            )
            for item in raw_items
        ]


class JsonFileMemory:
    def __init__(self, path: str | Path = ".memanto-demo-memory.json") -> None:
        self.path = Path(path)

    def remember(self, memory: Memory) -> None:
        memories = self._load()
        memories.append(asdict(memory))
        self.path.write_text(json.dumps(memories, indent=2), encoding="utf-8")

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        terms = {term.lower() for term in query.split() if len(term) > 2}
        scored: list[tuple[int, Memory]] = []
        for row in self._load():
            memory = Memory(**row)
            haystack = f"{memory.title} {memory.content}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, memory))
        return [memory for _, memory in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


def build_memory_adapter(*, offline: bool) -> MemoryAdapter:
    return JsonFileMemory() if offline else MemantoHttpMemory()

"""Memanto memory adapters used by the LangGraph example.

The live adapter uses Memanto's SDK client when `MOORCHEH_API_KEY` is
available.  The offline adapter stores the same typed memory records in a
small JSON file so reviewers can run the cross-session demo without secrets.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class MemoryHit:
    """Normalized memory record returned to the graph."""

    title: str
    content: str
    type: str = "fact"
    confidence: float = 0.8
    tags: list[str] | None = None

    def as_context_line(self) -> str:
        tags = ", ".join(self.tags or [])
        suffix = f" [{tags}]" if tags else ""
        return f"- {self.title}: {self.content}{suffix}"


class MemoryStore(Protocol):
    """Tiny interface LangGraph nodes use for long-term memory."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        ...

    def recall(self, *, query: str, limit: int = 5) -> list[MemoryHit]:
        ...


class OfflineJsonMemoryStore:
    """Credential-free persistent memory store for demos and tests.

    It deliberately persists to disk instead of keeping data in LangGraph
    state.  Running session A and session B as separate Python processes still
    proves cross-session recall.
    """

    def __init__(self, path: str | Path = ".memanto-langgraph-demo.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def _load(self) -> list[MemoryHit]:
        raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [MemoryHit(**item) for item in raw]

    def _save(self, memories: list[MemoryHit]) -> None:
        payload = [asdict(memory) for memory in memories]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        memory = MemoryHit(
            title=title,
            content=content,
            type=memory_type,
            confidence=confidence,
            tags=tags or [],
        )
        memories = self._load()
        memories.append(memory)
        self._save(memories)
        return {"memory_id": f"offline-{len(memories)}", "status": "stored"}

    def recall(self, *, query: str, limit: int = 5) -> list[MemoryHit]:
        terms = {part.lower() for part in query.replace("?", " ").split() if len(part) > 2}
        scored: list[tuple[int, MemoryHit]] = []
        for memory in self._load():
            haystack = f"{memory.title} {memory.content} {' '.join(memory.tags or [])}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, memory))

        if not scored:
            return self._load()[-limit:]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]


class LiveMemantoMemoryStore:
    """Thin wrapper around Memanto's SDK client.

    This is the production path for users with a Moorcheh/Memanto API key.  It
    creates or reuses an agent, activates a session, and uses the same
    `remember`/`recall` calls that the CLI exposes.
    """

    def __init__(self, api_key: str, agent_id: str = "langgraph-research-mentor") -> None:
        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph research mentor with durable Memanto memory",
            )
        except AgentAlreadyExistsError:
            pass
        self.client.activate_agent(agent_id)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )

    def recall(self, *, query: str, limit: int = 5) -> list[MemoryHit]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        memories: list[MemoryHit] = []
        for item in result.get("memories", []):
            memories.append(
                MemoryHit(
                    title=item.get("title", "memory"),
                    content=item.get("content", ""),
                    type=item.get("type", "fact"),
                    confidence=float(item.get("confidence", 0.8)),
                    tags=item.get("tags") or [],
                )
            )
        return memories


def build_memory_store(agent_id: str = "langgraph-research-mentor") -> MemoryStore:
    """Return a live Memanto store when credentials exist, else offline preview."""

    api_key = os.getenv("MOORCHEH_API_KEY") or os.getenv("MEMANTO_API_KEY")
    if api_key:
        return LiveMemantoMemoryStore(api_key=api_key, agent_id=agent_id)
    return OfflineJsonMemoryStore(Path(__file__).with_name(".memanto-langgraph-demo.json"))

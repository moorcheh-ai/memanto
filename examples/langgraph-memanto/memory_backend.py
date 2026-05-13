"""Memory backends used by the LangGraph + Memanto example."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Memory:
    """A normalized memory record returned by local and live backends."""

    id: str
    memory_type: str
    title: str
    content: str
    tags: list[str]
    confidence: float = 0.9


class MemoryBackend(Protocol):
    """Minimal memory interface the LangGraph workflow needs."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> Memory:
        """Persist a memory outside LangGraph's thread-scoped state."""

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        """Retrieve memories relevant to the current turn."""


class LocalJsonMemory:
    """Credential-free backend that mimics durable Memanto recall locally."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> Memory:
        memory = Memory(
            id=f"local-{uuid.uuid4().hex[:12]}",
            memory_type=memory_type,
            title=title,
            content=content,
            tags=tags,
            confidence=confidence,
        )
        memories = self._load()
        memories.append(memory)
        self._save(memories)
        return memory

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        scored: list[tuple[int, Memory]] = []
        for memory in self._load():
            text = " ".join([memory.title, memory.content, " ".join(memory.tags)])
            terms = _tokenize(text)
            score = len(query_terms & terms)
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: (-item[0], item[1].title))
        return [memory for _, memory in scored[:limit]]

    def clear(self) -> None:
        self._save([])

    def _load(self) -> list[Memory]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Memory(**item) for item in raw]

    def _save(self, memories: list[Memory]) -> None:
        payload = [asdict(memory) for memory in memories]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class MemantoMemory:
    """Live Memanto backend backed by the repository's ``SdkClient``."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph customer support memory demo",
    ) -> None:
        from memanto.app.utils.errors import AgentNotFoundError
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key)

        try:
            self.client.get_agent(agent_id)
        except AgentNotFoundError:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description=description,
            )

        self.client.activate_agent(agent_id)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> Memory:
        result = self.client.remember(
            self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            provenance="explicit_statement",
        )
        return Memory(
            id=str(result.get("memory_id", "")),
            memory_type=memory_type,
            title=title,
            content=content,
            tags=tags,
            confidence=confidence,
        )

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        result = self.client.recall(self.agent_id, query=query, limit=limit)
        return [_coerce_live_memory(item) for item in result.get("memories", [])]


def _coerce_live_memory(item: dict[str, Any]) -> Memory:
    content = str(item.get("content") or item.get("text") or item.get("memory") or "")
    title = str(item.get("title") or content[:72] or "Memanto memory")
    memory_type = str(item.get("type") or item.get("memory_type") or "fact")
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]

    return Memory(
        id=str(item.get("id") or item.get("memory_id") or ""),
        memory_type=memory_type,
        title=title,
        content=content,
        tags=[str(tag) for tag in tags],
        confidence=float(item.get("confidence") or item.get("score") or 0.9),
    )


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]*", text.lower())
        if len(token) > 2
    }


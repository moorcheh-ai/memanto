from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Memory:
    memory_type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    source_session: str


class MemoryStore(Protocol):
    def remember(self, agent_id: str, memory: Memory) -> str:
        ...

    def recall(self, agent_id: str, query: str, limit: int = 5) -> list[Memory]:
        ...


class LocalJsonMemoryStore:
    """Credential-free Memanto-compatible store for reviewer demos and tests."""

    def __init__(self, path: Path | None = None) -> None:
        default_path = Path(tempfile.gettempdir()) / "memanto-langgraph-memory.json"
        self.path = path or default_path

    def reset(self) -> None:
        self.path.unlink(missing_ok=True)

    def remember(self, agent_id: str, memory: Memory) -> str:
        data = self._read()
        data.setdefault(agent_id, []).append(asdict(memory))
        self._write(data)
        return f"local-{agent_id}-{len(data[agent_id])}"

    def recall(self, agent_id: str, query: str, limit: int = 5) -> list[Memory]:
        memories = [Memory(**item) for item in self._read().get(agent_id, [])]
        scored = sorted(
            memories,
            key=lambda memory: self._score(query, memory),
            reverse=True,
        )
        return [memory for memory in scored if self._score(query, memory) > 0][:limit]

    def _read(self) -> dict[str, list[dict[str, object]]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, list[dict[str, object]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _score(query: str, memory: Memory) -> int:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        haystack = " ".join([memory.title, memory.content, *memory.tags]).lower()
        memory_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        return len(query_tokens & memory_tokens)


class MemantoSdkMemoryStore:
    """Live Memanto adapter using the repository's SdkClient."""

    def __init__(self, api_key: str, client: object | None = None) -> None:
        if client is None:
            from memanto.cli.client.sdk_client import SdkClient

            client = SdkClient(api_key)
        self.client = client
        self._active_agent_id: str | None = None

    def _ensure_agent(self, agent_id: str) -> None:
        if self._active_agent_id == agent_id:
            return
        self.client.activate_agent(agent_id)
        self._active_agent_id = agent_id

    def remember(self, agent_id: str, memory: Memory) -> str:
        self._ensure_agent(agent_id)
        result = self.client.remember(
            agent_id=agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=f"langgraph:{memory.source_session}",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(self, agent_id: str, query: str, limit: int = 5) -> list[Memory]:
        self._ensure_agent(agent_id)
        result = self.client.recall(agent_id=agent_id, query=query, limit=limit)
        return [
            memory
            for memory in map(memory_from_sdk_result, result.get("memories", []))
            if memory
        ][:limit]


def memory_from_sdk_result(item: object) -> Memory | None:
    if not isinstance(item, dict):
        return None
    content = str(item.get("content") or item.get("text") or "").strip()
    if not content:
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            content = str(metadata.get("content") or metadata.get("text") or "").strip()
    if not content:
        return None

    source = str(item.get("source", "memanto"))
    if source.startswith("langgraph:"):
        source = source.split(":", 1)[1]
    tags = item.get("tags", [])
    return Memory(
        memory_type=str(item.get("type") or item.get("memory_type") or "fact"),
        title=str(item.get("title") or "Untitled"),
        content=content,
        confidence=float(item.get("confidence", 0.8)),
        tags=[str(tag) for tag in tags] if isinstance(tags, list) else [],
        source_session=source,
    )


def build_memory_store(backend: str | None = None) -> MemoryStore:
    resolved_backend = backend or os.getenv("MEMANTO_LANGGRAPH_BACKEND", "local")
    if resolved_backend == "memanto":
        api_key = os.environ["MOORCHEH_API_KEY"]
        return MemantoSdkMemoryStore(api_key)
    if resolved_backend != "local":
        raise ValueError(f"Unsupported backend: {resolved_backend}")
    return LocalJsonMemoryStore()

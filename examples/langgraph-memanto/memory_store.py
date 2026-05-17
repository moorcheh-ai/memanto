from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}


class LocalJsonMemoryStore:
    """Credential-free store that mirrors the Memanto remember/recall shape."""

    def __init__(self, path: str | Path = ".memanto-langgraph-local.json") -> None:
        self.path = Path(path)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_memory(memory_type, title, content)
        memories = self._load()
        memory = {
            "id": str(uuid.uuid4()),
            "type": memory_type,
            "title": title,
            "content": content,
            "tags": tags or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        memories.append(memory)
        self._save(memories)
        return {"memory_id": memory["id"], "status": "stored"}

    def recall(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        query_terms = _tokenize(query)
        scored = []
        for memory in self._load():
            haystack = " ".join(
                [
                    memory.get("title", ""),
                    memory.get("content", ""),
                    " ".join(memory.get("tags", [])),
                ]
            )
            score = len(query_terms & _tokenize(haystack))
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, list):
            raise ValueError(f"Expected a list of memories in {self.path}")
        return loaded

    def _save(self, memories: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(memories, handle, indent=2)


class MemantoMemoryStore:
    """Live Memanto-backed store for the same graph interface."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph support memory example",
    ) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description=description,
            )
        except Exception:
            # Existing agents are expected when the demo is re-run.
            pass
        self.client.activate_agent(agent_id)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=0.9,
            tags=tags or [],
            source="langgraph-example",
            provenance="explicit_statement",
        )

    def recall(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        return [_normalize_memanto_memory(memory) for memory in result.get("memories", [])]

    def close(self) -> None:
        self.client.deactivate_agent(self.agent_id)


def _normalize_memanto_memory(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": memory.get("id") or memory.get("memory_id"),
        "type": memory.get("type") or memory.get("memory_type"),
        "title": memory.get("title", "Untitled"),
        "content": memory.get("content", ""),
        "tags": memory.get("tags", []),
        "created_at": memory.get("created_at"),
    }


def _validate_memory(memory_type: str, title: str, content: str) -> None:
    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"Invalid memory_type: {memory_type}")
    if not title.strip():
        raise ValueError("title must be non-empty")
    if not content.strip():
        raise ValueError("content must be non-empty")


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }

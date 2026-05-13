"""Memory adapters for the LangGraph + Memanto example."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv


AGENT_ID = "langgraph-support-agent"
LOCAL_STORE_PATH = Path(__file__).with_name(".memanto_local_store.json")


@dataclass(frozen=True)
class MemoryItem:
    """Small normalized memory shape used by the example graph."""

    title: str
    content: str
    memory_type: str = "fact"
    confidence: float = 0.9
    tags: tuple[str, ...] = ()


class MemoryStore(Protocol):
    """Protocol shared by the live Memanto and local fallback adapters."""

    def remember(self, item: MemoryItem) -> str:
        """Store a memory and return its identifier."""

    def recall(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """Recall memories relevant to the query."""

    def close(self) -> None:
        """Release any active session resources."""


class LocalJsonMemoryStore:
    """Deterministic local fallback for tests and no-key demos."""

    def __init__(self, path: Path = LOCAL_STORE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, item: MemoryItem) -> str:
        rows = self._load()
        memory_id = f"local-{len(rows) + 1}"
        rows.append({"id": memory_id, **asdict(item), "tags": list(item.tags)})
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return memory_id

    def recall(self, query: str, limit: int = 5) -> list[MemoryItem]:
        query_terms = _terms(query)
        ranked = []
        for row in self._load():
            text = " ".join(
                [
                    row.get("title", ""),
                    row.get("content", ""),
                    " ".join(row.get("tags", [])),
                ]
            )
            score = len(query_terms.intersection(_terms(text)))
            if score:
                ranked.append((score, row))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            MemoryItem(
                title=row["title"],
                content=row["content"],
                memory_type=row.get("memory_type", "fact"),
                confidence=float(row.get("confidence", 0.9)),
                tags=tuple(row.get("tags", [])),
            )
            for _, row in ranked[:limit]
        ]

    def close(self) -> None:
        return None

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


class MemantoSdkMemoryStore:
    """Live Memanto adapter used when MOORCHEH_API_KEY is available."""

    def __init__(self, api_key: str, agent_id: str = AGENT_ID) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description="LangGraph support agent with persistent Memanto memory",
            )
        except Exception:
            pass
        self.client.activate_agent(agent_id)

    def remember(self, item: MemoryItem) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=item.memory_type,
            title=item.title,
            content=item.content,
            confidence=item.confidence,
            tags=list(item.tags),
            source="langgraph-example",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(self, query: str, limit: int = 5) -> list[MemoryItem]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        memories = []
        for row in result.get("memories", []):
            memories.append(
                MemoryItem(
                    title=str(row.get("title", "Untitled")),
                    content=str(row.get("content", "")),
                    memory_type=str(row.get("type", row.get("memory_type", "fact"))),
                    confidence=float(row.get("confidence", 0.9)),
                    tags=tuple(row.get("tags", []) or []),
                )
            )
        return memories

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


def create_memory_store(force_local: bool = False) -> MemoryStore:
    """Create a live Memanto store when configured, otherwise local fallback."""

    load_dotenv()
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if api_key and not force_local:
        return MemantoSdkMemoryStore(api_key)
    return LocalJsonMemoryStore()


def reset_local_store(path: Path = LOCAL_STORE_PATH) -> None:
    """Remove local fallback memories so the demo starts clean."""

    if path.exists():
        path.unlink()


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))

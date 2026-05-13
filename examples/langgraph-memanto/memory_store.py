"""Memanto-backed and local-preview memory stores for the example graph."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from state import MemoryHit

DEFAULT_AGENT_ID = "langgraph-support-demo"
PREVIEW_DIR = Path(__file__).resolve().parent / ".memanto-preview"
PREVIEW_STORE = PREVIEW_DIR / "memories.jsonl"


class MemoryStore(Protocol):
    """Small interface used by the LangGraph nodes."""

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.86,
    ) -> dict[str, Any]:
        """Persist one memory."""

    def recall(self, query: str, limit: int = 5) -> list[MemoryHit]:
        """Return relevant memories for a query."""

    def close(self) -> None:
        """Release any session resources."""


def normalize_memory(raw: dict[str, Any], score: float | None = None) -> MemoryHit:
    """Normalize Memanto SDK and preview records into one shape."""
    raw_score = score
    if raw_score is None:
        raw_score = float(raw.get("score") or raw.get("similarity") or 0.0)

    return {
        "title": str(raw.get("title") or raw.get("memory_title") or "Memory"),
        "content": str(raw.get("content") or raw.get("text") or raw.get("memory") or ""),
        "type": str(raw.get("type") or raw.get("memory_type") or "fact"),
        "score": raw_score,
        "tags": list(raw.get("tags") or []),
    }


class PreviewMemoryStore:
    """A deterministic file-backed store for running the demo without secrets."""

    def __init__(self, path: Path = PREVIEW_STORE, reset: bool = False) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.path.exists():
            self.path.unlink()

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.86,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "type": memory_type,
            "title": title[:100],
            "content": content[:500],
            "tags": tags or [],
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return {"memory_id": record["id"], "status": "stored-preview"}

    def recall(self, query: str, limit: int = 5) -> list[MemoryHit]:
        records = self._read_records()
        query_terms = _tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for record in records:
            haystack = " ".join(
                [
                    record.get("title", ""),
                    record.get("content", ""),
                    " ".join(record.get("tags", [])),
                ]
            )
            record_terms = _tokenize(haystack)
            overlap = len(query_terms & record_terms)
            if overlap:
                score = overlap / max(len(query_terms), 1)
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [normalize_memory(record, score=score) for score, record in scored[:limit]]

    def close(self) -> None:
        return None

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records


@dataclass
class MemantoMemoryStore:
    """Thin adapter over Memanto's SDK client."""

    client: Any
    agent_id: str

    @classmethod
    def from_env(
        cls,
        agent_id: str = DEFAULT_AGENT_ID,
        description: str = "LangGraph support demo with cross-session memory",
    ) -> MemantoMemoryStore:
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MOORCHEH_API_KEY is required for live mode. "
                "Run without --live for the credential-free preview."
            )

        from memanto.cli.client.sdk_client import SdkClient

        client = SdkClient(api_key)
        try:
            client.get_agent(agent_id)
        except Exception as exc:
            if exc.__class__.__name__ != "AgentNotFoundError":
                raise
            client.create_agent(agent_id, pattern="support", description=description)

        client.activate_agent(agent_id)
        return cls(client=client, agent_id=agent_id)

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.86,
    ) -> dict[str, Any]:
        return self.client.remember(
            self.agent_id,
            memory_type,
            title[:100],
            content[:500],
            confidence=confidence,
            tags=tags or [],
            source="langgraph-support-demo",
        )

    def recall(self, query: str, limit: int = 5) -> list[MemoryHit]:
        result = self.client.recall(self.agent_id, query, limit=limit)
        return [normalize_memory(memory) for memory in result.get("memories", [])]

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            return None


def build_memory_store(
    live: bool = False,
    agent_id: str = DEFAULT_AGENT_ID,
    reset_preview: bool = False,
) -> MemoryStore:
    """Create the requested memory store."""
    if live:
        return MemantoMemoryStore.from_env(agent_id=agent_id)
    return PreviewMemoryStore(reset=reset_preview)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower())
        if token
        not in {
            "and",
            "are",
            "can",
            "for",
            "the",
            "this",
            "that",
            "what",
            "with",
            "you",
            "your",
        }
    }

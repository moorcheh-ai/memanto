"""Small Memanto client used by the LangGraph example."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class Memory:
    content: str
    type: str = "fact"
    title: str | None = None
    confidence: float = 0.9
    tags: list[str] | None = None


class MemantoMemoryClient:
    """HTTP adapter for a local Memanto server."""

    def __init__(self, base_url: str, agent_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.session_token: str | None = None
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def setup(self) -> None:
        self._ensure_agent()
        self.session_token = self._activate_agent()

    def remember(self, memory: Memory) -> dict[str, Any]:
        if not self.session_token:
            self.setup()

        payload = {
            "content": memory.content,
            "type": memory.type,
            "title": memory.title,
            "confidence": memory.confidence,
            "tags": memory.tags or [],
            "source": "langgraph-memanto-example",
            "provenance": "explicit_statement",
        }
        response = self.client.post(
            f"/api/v2/agents/{self.agent_id}/remember",
            headers={"X-Session-Token": self.session_token or ""},
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.session_token:
            self.setup()

        response = self.client.post(
            f"/api/v2/agents/{self.agent_id}/recall",
            headers={"X-Session-Token": self.session_token or ""},
            json={"query": query, "limit": limit},
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        return body.get("results") or body.get("memories") or []

    def _ensure_agent(self) -> None:
        payload = {
            "agent_id": self.agent_id,
            "pattern": "support",
            "description": "LangGraph support agent with persistent Memanto memory",
        }
        response = self.client.post("/api/v2/agents", json=payload)
        if response.status_code not in {200, 201, 409, 422}:
            response.raise_for_status()

    def _activate_agent(self) -> str:
        response = self.client.post(f"/api/v2/agents/{self.agent_id}/activate")
        response.raise_for_status()
        body = response.json()
        return body["session_token"]


class JsonMemoryClient:
    """Local fallback for recordings and CI without a Memanto API key."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def setup(self) -> None:
        if not self.store_path.exists():
            self.store_path.write_text("[]\n", encoding="utf-8")

    def remember(self, memory: Memory) -> dict[str, Any]:
        self.setup()
        records = self._load()
        record = {
            "content": memory.content,
            "type": memory.type,
            "title": memory.title or memory.content[:80],
            "confidence": memory.confidence,
            "tags": memory.tags or [],
        }
        records.append(record)
        self.store_path.write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )
        return {"status": "stored", "memory_id": len(records)}

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        self.setup()
        terms = {term.lower() for term in query.split() if len(term) > 2}
        records = self._load()

        def score(record: dict[str, Any]) -> int:
            text = " ".join(
                [
                    record.get("content", ""),
                    record.get("title", ""),
                    " ".join(record.get("tags") or []),
                ]
            ).lower()
            return sum(1 for term in terms if term in text)

        ranked = sorted(records, key=score, reverse=True)
        return [record for record in ranked[:limit] if score(record) > 0]

    def _load(self) -> list[dict[str, Any]]:
        return json.loads(self.store_path.read_text(encoding="utf-8"))

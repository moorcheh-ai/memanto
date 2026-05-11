"""Memory adapter used by the LangGraph + Memanto example.

The real adapter delegates to Memanto's SdkClient. The fallback adapter keeps
the example runnable for reviewers who do not have a Moorcheh API key handy.
Both adapters expose the same tiny surface: remember, recall, and answer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class MemoryClient(Protocol):
    """Small memory interface consumed by the LangGraph nodes."""

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        """Persist one memory."""

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return relevant memories."""

    def answer(self, question: str, limit: int = 5) -> str:
        """Answer a question from memory context."""


@dataclass
class MemantoMemoryClient:
    """Adapter around the repository's Memanto SDK client."""

    api_key: str
    agent_id: str
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self._client = SdkClient(self.api_key)
        try:
            self._client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description="LangGraph customer-success demo memory.",
            )
        except Exception:
            # Reusing an existing demo agent is expected during repeated runs.
            pass
        self._client.activate_agent(self.agent_id)

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        self._client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=0.9,
            tags=tags or ["langgraph-demo"],
            source="langgraph-demo",
        )

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
        )
        return result.get("memories", [])

    def answer(self, question: str, limit: int = 5) -> str:
        result = self._client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=limit,
        )
        return result.get("answer", "No answer generated.")


@dataclass
class LocalReviewMemoryClient:
    """Tiny local fallback with the same interface as the Memanto adapter."""

    store_path: Path
    agent_id: str

    def _load(self) -> list[dict[str, Any]]:
        if not self.store_path.exists():
            return []
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _save(self, memories: list[dict[str, Any]]) -> None:
        self.store_path.write_text(json.dumps(memories, indent=2), encoding="utf-8")

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        memories = self._load()
        memories.append(
            {
                "agent_id": self.agent_id,
                "type": memory_type,
                "title": title,
                "content": content,
                "tags": tags or ["langgraph-demo"],
            }
        )
        self._save(memories)

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        scored = []
        for memory in self._load():
            text = f"{memory['title']} {memory['content']}".lower()
            score = sum(1 for term in query_terms if term in text)
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def answer(self, question: str, limit: int = 5) -> str:
        memories = self.recall(question, limit=limit)
        if not memories:
            return "I do not have any relevant memories yet."
        facts = "; ".join(memory["content"] for memory in memories)
        return f"Based on persistent memory: {facts}"


def create_memory_client(agent_id: str) -> MemoryClient:
    """Create a real Memanto client when possible, otherwise local review mode."""

    api_key = os.getenv("MOORCHEH_API_KEY")
    if api_key:
        return MemantoMemoryClient(api_key=api_key, agent_id=agent_id)

    return LocalReviewMemoryClient(
        store_path=Path(__file__).with_name(".local_memanto_review_store.json"),
        agent_id=agent_id,
    )

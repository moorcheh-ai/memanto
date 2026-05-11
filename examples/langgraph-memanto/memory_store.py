"""
Memanto memory adapters for the LangGraph example.

The production adapter talks to Memanto through SdkClient. The in-memory
adapter keeps the demo and tests runnable without external API calls while
preserving the same interface used by the graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

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


class MemoryStore(Protocol):
    """Minimal interface the LangGraph nodes need from a memory backend."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a memory and return backend metadata."""

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories for a natural-language query."""

    def close(self) -> None:
        """Release any active resources or sessions."""


class MemantoMemoryStore:
    """Production MemoryStore backed by Memanto's SdkClient."""

    backend_name = "Memanto"

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph long-term memory demo",
        session_hours: int = 6,
    ) -> None:
        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description=description,
            )
            logger.info("Created Memanto agent '%s'", agent_id)
        except Exception as exc:
            logger.info("Reusing existing Memanto agent '%s': %s", agent_id, exc)

        self.client.activate_agent(agent_id, duration_hours=session_hours)
        logger.info("Activated Memanto session for '%s'", agent_id)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-demo",
            provenance="explicit_statement",
        )

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return list(result.get("memories", []))

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception as exc:
            logger.warning("Could not deactivate Memanto agent '%s': %s", self.agent_id, exc)


@dataclass
class InMemoryMemoryStore:
    """Tiny MemoryStore used by --mock mode and tests."""

    backend_name = "the in-memory demo store"

    memories: list[dict[str, Any]] = field(default_factory=list)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(f"Unsupported memory_type: {memory_type}")

        memory_id = f"mock-{uuid4().hex[:12]}"
        memory = {
            "id": memory_id,
            "memory_id": memory_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "confidence": confidence,
            "tags": tags or [],
        }
        self.memories.append(memory)
        return {"memory_id": memory_id, "status": "stored", "confidence": confidence}

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query_terms = _tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []

        for memory in self.memories:
            if memory_types and memory.get("type") not in memory_types:
                continue
            searchable = " ".join(
                [
                    str(memory.get("type", "")),
                    str(memory.get("title", "")),
                    str(memory.get("content", "")),
                    " ".join(memory.get("tags", [])),
                ]
            )
            score = len(query_terms & _tokenize(searchable))
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def close(self) -> None:
        return None


def format_memory(memory: dict[str, Any]) -> str:
    """Render a memory consistently for demo output."""
    memory_type = memory.get("type", "unknown")
    title = memory.get("title", "Untitled")
    content = memory.get("content", "")
    confidence = memory.get("confidence", "n/a")
    return f"[{memory_type}] {title} ({confidence}): {content}"


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in text.split():
        token = raw_token.strip(".,!?;:()[]{}'\"").lower()
        if len(token) <= 2:
            continue
        tokens.add(token)
        if token.endswith("s") and len(token) > 4:
            tokens.add(token[:-1])
        if token.endswith("ers") and len(token) > 5:
            tokens.add(token[:-1])
    return tokens

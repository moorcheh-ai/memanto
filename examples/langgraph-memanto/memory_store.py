"""Memanto-backed long-term memory adapter for the LangGraph example."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LongTermMemory(Protocol):
    """Small interface used by the LangGraph nodes."""

    def setup(self) -> None:
        """Prepare the memory namespace."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> str:
        """Persist a memory and return its identifier."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return relevant memories."""


class MemantoLongTermMemory:
    """Thin wrapper around Memanto's SDK client."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

    def setup(self) -> None:
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="langgraph",
                description="LangGraph support assistant with cross-session memory",
            )
        except Exception:
            # The demo is intentionally idempotent. Reusing an existing agent is OK.
            pass

        self.client.activate_agent(self.agent_id, duration_hours=24)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-memanto-example",
            provenance="workflow_node",
        )
        return str(result.get("memory_id", "unknown"))

    def recall(
        self,
        query: str,
        *,
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


@dataclass
class InMemoryLongTermMemory:
    """Deterministic in-process memory used for offline demos and tests."""

    agent_id: str = "offline-langgraph-support"
    memories: list[dict[str, Any]] = field(default_factory=list)

    def setup(self) -> None:
        return None

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> str:
        memory_id = f"mem-{len(self.memories) + 1}"
        self.memories.append(
            {
                "id": memory_id,
                "memory_id": memory_id,
                "type": memory_type,
                "title": title,
                "content": content,
                "tags": tags or [],
                "confidence": confidence,
            }
        )
        return memory_id

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        ranked: list[tuple[int, dict[str, Any]]] = []

        for memory in self.memories:
            if memory_types and memory.get("type") not in memory_types:
                continue
            haystack = " ".join(
                [
                    str(memory.get("title", "")),
                    str(memory.get("content", "")),
                    " ".join(memory.get("tags", [])),
                ]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                ranked.append((score, memory))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]


def format_memories(memories: list[dict[str, Any]]) -> str:
    """Render retrieved memories for deterministic prompts and terminal output."""

    if not memories:
        return "No relevant memories found."

    lines = []
    for memory in memories:
        memory_type = memory.get("type", "memory")
        title = memory.get("title", "Untitled")
        content = memory.get("content", "")
        lines.append(f"- [{memory_type}] {title}: {content}")
    return "\n".join(lines)

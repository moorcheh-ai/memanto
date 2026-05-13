from __future__ import annotations

from typing import Any, Protocol


class MemantoClient(Protocol):
    def remember(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def recall(self, **kwargs: Any) -> dict[str, Any]:
        ...


def _memory_content(memory: Any) -> str | None:
    if isinstance(memory, str):
        return memory

    if not isinstance(memory, dict):
        return None

    for key in ("content", "text", "summary"):
        value = memory.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested = memory.get("memory")
    if isinstance(nested, dict):
        return _memory_content(nested)

    metadata = memory.get("metadata")
    if isinstance(metadata, dict):
        return _memory_content(metadata)

    return None


class MemantoMemoryAdapter:
    def __init__(self, client: MemantoClient, agent_id: str) -> None:
        self.client = client
        self.agent_id = agent_id

    def store_customer_preference(
        self,
        *,
        customer_id: str,
        preference: str,
        source_ticket: str,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=f"Preference for {customer_id}",
            content=preference,
            confidence=0.9,
            tags=["langgraph-demo", f"customer:{customer_id}", f"ticket:{source_ticket}"],
            source="langgraph-support-demo",
            provenance="explicit_statement",
        )

    def recall_customer_context(
        self,
        customer_id: str,
        *,
        limit: int = 4,
    ) -> list[str]:
        response = self.client.recall(
            agent_id=self.agent_id,
            query=f"support context and preferences for customer {customer_id}",
            limit=limit,
            type=["preference", "fact", "decision", "context", "event"],
            tags=["langgraph-demo", f"customer:{customer_id}"],
        )

        raw_memories = response.get("memories", [])
        normalized: list[str] = []
        for memory in raw_memories:
            content = _memory_content(memory)
            if content:
                normalized.append(content)

        return normalized


def format_context(memories: list[str]) -> str:
    if not memories:
        return "No prior Memanto context found for this customer."

    return "\n".join(f"- {memory}" for memory in memories)

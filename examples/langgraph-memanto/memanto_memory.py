"""Memanto helpers for the LangGraph cross-session memory example."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class MemoryClient(Protocol):
    """Small subset of Memanto's SdkClient used by this example."""

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
        provenance: str,
    ) -> dict[str, Any]: ...

    def recall(
        self, *, agent_id: str, query: str, limit: int = 5
    ) -> dict[str, Any]: ...


@dataclass
class InMemoryMemantoClient:
    """Deterministic stand-in for Memanto used by the dry-run and tests."""

    memories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
        provenance: str,
    ) -> dict[str, Any]:
        memory_id = f"dry-{len(self.memories.get(agent_id, [])) + 1}"
        memory = {
            "memory_id": memory_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "confidence": confidence,
            "tags": tags,
            "source": source,
            "provenance": provenance,
        }
        self.memories.setdefault(agent_id, []).append(memory)
        return {"memory_id": memory_id, "memory": memory}

    def recall(self, *, agent_id: str, query: str, limit: int = 5) -> dict[str, Any]:
        terms = {part.lower() for part in query.replace("-", " ").split() if part}
        scored: list[tuple[int, dict[str, Any]]] = []
        for memory in self.memories.get(agent_id, []):
            searchable = " ".join(
                [
                    str(memory.get("title", "")),
                    str(memory.get("content", "")),
                    " ".join(memory.get("tags", [])),
                ]
            ).lower()
            score = sum(1 for term in terms if term in searchable)
            if score:
                scored.append((score, memory))

        if not scored:
            scored = [(0, memory) for memory in self.memories.get(agent_id, [])]

        scored.sort(key=lambda item: item[0], reverse=True)
        return {"memories": [memory for _, memory in scored[:limit]]}


def create_sdk_client(api_key: str) -> Any:
    """Create the real Memanto SDK client lazily so dry-runs need no API key."""
    from memanto.cli.client.sdk_client import SdkClient

    return SdkClient(api_key=api_key)


def setup_memanto_session(
    client: Any,
    *,
    agent_id: str,
    description: str = "LangGraph customer-support memory demo",
) -> None:
    """Create and activate the shared Memanto agent namespace if supported."""
    if isinstance(client, InMemoryMemantoClient):
        return

    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="support",
            description=description,
        )
    except Exception:
        # Reusing an existing demo namespace is expected.
        pass
    client.activate_agent(agent_id, duration_hours=6)


def remember_profile(
    client: MemoryClient, *, agent_id: str, profile: dict[str, Any]
) -> str:
    """Persist a customer profile as typed memories outside LangGraph state."""
    customer = profile["customer"]
    product = profile["product"]
    deadline = profile["deadline"]
    preference = profile["preference"]

    result = client.remember(
        agent_id=agent_id,
        memory_type="fact",
        title=f"{customer} support profile",
        content=(
            f"{customer} is evaluating {product}; deadline is {deadline}; "
            f"prefers {preference}."
        ),
        confidence=0.95,
        tags=["langgraph", "customer-support", customer.lower()],
        source="langgraph-demo",
        provenance="explicit_statement",
    )
    return str(result["memory_id"])


def recall_profile(
    client: MemoryClient,
    *,
    agent_id: str,
    customer: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Recall customer memories without relying on the current graph state."""
    result = client.recall(
        agent_id=agent_id,
        query=f"{customer} support profile product deadline preference",
        limit=limit,
    )
    return list(result.get("memories", []))


def render_recalled_memories(memories: list[dict[str, Any]]) -> str:
    """Format memories for the response node and README transcript."""
    if not memories:
        return "No persistent memories were found."

    lines = []
    for memory in memories:
        tags = ", ".join(memory.get("tags", []))
        tag_suffix = f" [{tags}]" if tags else ""
        lines.append(
            f"- {memory.get('title', 'Untitled')}{tag_suffix}: "
            f"{memory.get('content', '')}"
        )
    return "\n".join(lines)


def dump_json(data: dict[str, Any]) -> str:
    """Stable pretty-printer used by the demo scripts."""
    return json.dumps(data, indent=2, sort_keys=True)

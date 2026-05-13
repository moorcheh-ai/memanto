"""
LangGraph + Memanto customer support example.

The LangGraph state is intentionally short lived. Cross-session recall comes
from the injected memory store, which can be the real Memanto SDK adapter or an
in-memory adapter for local review.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict

DEFAULT_AGENT_ID = "langgraph-support-agent"
DEFAULT_CUSTOMER_ID = "ada-lovelace"
logger = logging.getLogger(__name__)


class SupportState(TypedDict, total=False):
    """State carried by a single LangGraph invocation."""

    customer_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    memory_to_write: dict[str, Any] | None


class LongTermMemory(Protocol):
    """Small memory surface the graph needs from Memanto."""

    def recall(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        """Return memories relevant to a graph run."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Persist one memory for future graph runs."""


@dataclass
class InMemoryMemoryStore:
    """Credential-free adapter for local review and tests."""

    memories: list[dict[str, Any]] = field(default_factory=list)

    def recall(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        ranked = []
        for index, memory in enumerate(self.memories):
            haystack = " ".join(
                str(memory.get(key, "")) for key in ("title", "content", "type")
            )
            score = len(query_tokens & _tokens(haystack))
            if score:
                ranked.append((score, index, memory))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [memory for _, _, memory in ranked[:limit]]

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        memory_id = f"preview-{len(self.memories) + 1}"
        memory = {
            "memory_id": memory_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "tags": tags,
            "confidence": confidence,
        }
        self.memories.append(memory)
        return memory


@dataclass
class MemantoMemoryStore:
    """Memanto SDK adapter used by the LangGraph nodes."""

    api_key: str
    agent_id: str = DEFAULT_AGENT_ID
    duration_hours: int = 6
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self._client = SdkClient(api_key=self.api_key)
        try:
            self._client.create_agent(
                self.agent_id,
                pattern="support",
                description="LangGraph support workflow long-term memory",
            )
        except AgentAlreadyExistsError:
            pass
        self._client.activate_agent(self.agent_id, duration_hours=self.duration_hours)

    def close(self) -> None:
        try:
            self._client.deactivate_agent(self.agent_id)
        except Exception as exc:
            logger.warning(
                "Failed to deactivate Memanto agent %s: %s",
                self.agent_id,
                exc,
            )

    def recall(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=["fact", "preference", "event", "observation"],
        )
        return list(result.get("memories", []))

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        return dict(
            self._client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tags,
                source="langgraph-support-agent",
                provenance="explicit_statement",
            )
        )


def build_graph(memory: LongTermMemory):
    """Build the customer-support graph with Memanto-backed memory nodes."""

    from langgraph.graph import END, StateGraph

    graph = StateGraph(SupportState)
    graph.add_node("load_memanto_context", _load_context_node(memory))
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_followup_memory", _write_memory_node(memory))

    graph.set_entry_point("load_memanto_context")
    graph.add_edge("load_memanto_context", "draft_response")
    graph.add_edge("draft_response", "write_followup_memory")
    graph.add_edge("write_followup_memory", END)
    return graph.compile()


def draft_response(state: SupportState) -> dict[str, str]:
    """Draft a deterministic response from the current message plus memory."""

    customer_id = state.get("customer_id", DEFAULT_CUSTOMER_ID)
    memories = state.get("recalled_memories", [])
    message = state.get("message", "")

    if memories:
        context = format_memories(memories)
        response = (
            f"I found prior Memanto context for {customer_id}:\n"
            f"{context}\n\n"
            "Support reply: acknowledge the stored context first, then answer "
            f"the new request: {message}"
        )
    else:
        response = (
            f"No prior Memanto context was found for {customer_id}. "
            f"Support reply: handle the new request directly: {message}"
        )

    return {"response": response}


def extract_customer_memory(state: SupportState) -> dict[str, Any] | None:
    """Convert the current interaction into one durable customer fact."""

    message = state.get("message", "").strip()
    if not message:
        return None

    customer_id = state.get("customer_id", DEFAULT_CUSTOMER_ID)
    content = f"{customer_id}: {message}"
    title = f"{customer_id} support context"

    return {
        "memory_type": "fact",
        "title": title[:100],
        "content": content[:500],
        "tags": ["langgraph", "support", "cross-session", customer_id],
        "confidence": 0.9,
    }


def format_memories(memories: list[dict[str, Any]]) -> str:
    """Render recalled memories for the deterministic response node."""

    lines = []
    for index, memory in enumerate(memories, start=1):
        title = memory.get("title") or "Untitled"
        content = memory.get("content") or memory.get("text") or ""
        memory_type = memory.get("type") or "memory"
        lines.append(f"{index}. [{memory_type}] {title}: {content}")
    return "\n".join(lines)


def _load_context_node(memory: LongTermMemory):
    def load_context(state: SupportState) -> dict[str, list[dict[str, Any]]]:
        customer_id = state.get("customer_id", DEFAULT_CUSTOMER_ID)
        query = f"{customer_id} {state.get('message', '')}"
        return {"recalled_memories": memory.recall(query, limit=4)}

    return load_context


def _write_memory_node(memory: LongTermMemory):
    def write_memory(state: SupportState) -> dict[str, dict[str, Any] | None]:
        payload = extract_customer_memory(state)
        if payload is None:
            return {"memory_to_write": None}

        result = memory.remember(**payload)
        memory_id = result.get("memory_id") or result.get("id")
        return {"memory_to_write": {**payload, "memory_id": memory_id}}

    return write_memory


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))

"""A LangGraph workflow with Memanto-backed long-term memory.

The graph deliberately avoids an LLM dependency so the integration is easy to
run: LangGraph orchestrates memory extraction, storage, recall, and response
composition; Memanto supplies durable semantic memory across graph runs.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from memory_store import MemoryStore, format_memory

MAX_TITLE_LENGTH = 100
MAX_CONTENT_LENGTH = 500


class MemoryState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    user_id: str
    message: str
    memories_to_store: list[dict[str, Any]]
    stored_memory_ids: list[str]
    recalled_memories: list[dict[str, Any]]
    response: str


def build_memory_graph(memory_store: MemoryStore):
    """Build and compile the LangGraph memory workflow."""

    def extract_memory_node(state: MemoryState) -> dict[str, Any]:
        return {
            "memories_to_store": extract_memories_from_message(
                state.get("message", ""),
                user_id=state.get("user_id", "user"),
            )
        }

    def store_memory_node(state: MemoryState) -> dict[str, Any]:
        stored_ids: list[str] = []
        for memory in state.get("memories_to_store", []):
            result = memory_store.remember(
                memory_type=memory["type"],
                title=memory["title"],
                content=memory["content"],
                confidence=memory.get("confidence", 0.85),
                tags=memory.get("tags", []),
            )
            stored_ids.append(result.get("memory_id", "unknown"))
        return {"stored_memory_ids": stored_ids}

    def recall_memory_node(state: MemoryState) -> dict[str, Any]:
        message = state.get("message", "")
        recalled = memory_store.recall(query=message, limit=5)
        return {"recalled_memories": recalled}

    def answer_node(state: MemoryState) -> dict[str, Any]:
        recalled = state.get("recalled_memories", [])
        stored_ids = state.get("stored_memory_ids", [])

        if recalled:
            backend_name = getattr(memory_store, "backend_name", "long-term memory")
            lines = [f"I found these persisted memories in {backend_name}:"]
            lines.extend(f"- {format_memory(memory)}" for memory in recalled)
            if stored_ids:
                lines.append(f"\nI also stored {len(stored_ids)} new memory item(s).")
            return {"response": "\n".join(lines)}

        if stored_ids:
            return {
                "response": (
                    f"Stored {len(stored_ids)} new memory item(s). "
                    "Ask me about them in another graph run to prove persistence."
                )
            }

        return {
            "response": (
                "I did not find matching long-term memories yet. "
                "Tell me a preference, fact, goal, or instruction to remember."
            )
        }

    workflow = StateGraph(MemoryState)
    workflow.add_node("extract_memory", extract_memory_node)
    workflow.add_node("store_memory", store_memory_node)
    workflow.add_node("recall_memory", recall_memory_node)
    workflow.add_node("answer", answer_node)

    workflow.add_edge(START, "extract_memory")
    workflow.add_edge("extract_memory", "store_memory")
    workflow.add_edge("store_memory", "recall_memory")
    workflow.add_edge("recall_memory", "answer")
    workflow.add_edge("answer", END)

    return workflow.compile()


def extract_memories_from_message(message: str, *, user_id: str) -> list[dict[str, Any]]:
    """Extract explicit long-term memories from a user message.

    This intentionally small rule set keeps the example deterministic. In a
    production agent, this node can be swapped for an LLM classifier while the
    Memanto storage and recall nodes stay the same.
    """

    memories: list[dict[str, Any]] = []
    normalized_message = " ".join(message.split())

    for match in re.finditer(r"\bmy name is\s+([^.;,!]+)", normalized_message, re.I):
        name = _clean_fragment(match.group(1))
        memories.append(
            _memory(
                memory_type="fact",
                title="User name",
                content=f"{user_id}'s name is {name}.",
                tags=["identity", user_id],
            )
        )

    for match in re.finditer(
        r"\b(?:i prefer|i like|i love)\s+([^.;]+)",
        normalized_message,
        re.I,
    ):
        preference = _clean_fragment(match.group(1))
        memories.append(
            _memory(
                memory_type="preference",
                title="User preference",
                content=f"{user_id} prefers {preference}.",
                tags=["preference", user_id],
            )
        )

    for match in re.finditer(
        r"\ballergic to\s+(.+?)(?=\s+and\s+i\b|[.;,!]|$)",
        normalized_message,
        re.I,
    ):
        allergy = _clean_fragment(match.group(1))
        memories.append(
            _memory(
                memory_type="fact",
                title="User allergy",
                content=f"{user_id} is allergic to {allergy}.",
                tags=["health", "allergy", user_id],
                confidence=0.95,
            )
        )

    for match in re.finditer(r"\bmy project is\s+([^.;]+)", normalized_message, re.I):
        project = _clean_fragment(match.group(1))
        memories.append(
            _memory(
                memory_type="context",
                title="User project",
                content=f"{user_id}'s current project is {project}.",
                tags=["project", user_id],
            )
        )

    for match in re.finditer(r"\bremember that\s+([^.;]+)", normalized_message, re.I):
        instruction = _clean_fragment(match.group(1))
        memories.append(
            _memory(
                memory_type="instruction",
                title="Remembered instruction",
                content=instruction,
                tags=["instruction", user_id],
            )
        )

    return memories


def _memory(
    *,
    memory_type: str,
    title: str,
    content: str,
    tags: list[str],
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "type": memory_type,
        "title": title[:MAX_TITLE_LENGTH],
        "content": content[:MAX_CONTENT_LENGTH],
        "confidence": confidence,
        "tags": tags,
    }


def _clean_fragment(value: str) -> str:
    return value.strip().strip(" .,!?:;\n\t")

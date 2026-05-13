"""LangGraph workflow that uses Memanto as durable memory outside graph state."""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from memory_store import MemoryHit, MemoryStore


class ResearchState(TypedDict, total=False):
    """LangGraph state for one short research-support turn."""

    session: str
    user_message: str
    recalled_memories: list[MemoryHit]
    response: str
    memory_to_store: dict[str, object]
    stored_memory_id: str


def _memory_context(memories: list[MemoryHit]) -> str:
    if not memories:
        return "No durable memories found."
    return "\n".join(memory.as_context_line() for memory in memories)


def build_research_graph(store: MemoryStore):
    """Build and compile the LangGraph state machine.

    The graph keeps only transient fields in LangGraph state.  Long-term facts
    are read from and written to Memanto via `store`, so a new process/session
    can recall what a previous graph execution saved.
    """

    def recall_context(state: ResearchState) -> ResearchState:
        query = state["user_message"]
        return {"recalled_memories": store.recall(query=query, limit=5)}

    def answer_with_memory(state: ResearchState) -> ResearchState:
        message = state["user_message"]
        context = _memory_context(state.get("recalled_memories", []))
        response = (
            "Research mentor response\n"
            f"Question: {message}\n\n"
            "Durable Memanto context used:\n"
            f"{context}\n\n"
            "Next step: keep new user/project facts in Memanto so the next "
            "LangGraph run starts with durable context instead of an empty state."
        )
        return {"response": response}

    def extract_memory(state: ResearchState) -> ResearchState:
        message = state["user_message"]
        if "remember" not in message.lower():
            return {}

        content = re.split(r"\bremember\b", message, maxsplit=1, flags=re.IGNORECASE)[-1]
        content = content.strip(" :.-") or message
        return {
            "memory_to_store": {
                "memory_type": "fact",
                "title": "Research preference captured by LangGraph",
                "content": content,
                "confidence": 0.88,
                "tags": ["langgraph", "research-mentor", "cross-session"],
            }
        }

    def store_memory(state: ResearchState) -> ResearchState:
        payload = state.get("memory_to_store")
        if not payload:
            return {}
        result = store.remember(**payload)  # type: ignore[arg-type]
        return {"stored_memory_id": str(result.get("memory_id", "stored"))}

    graph = StateGraph(ResearchState)
    graph.add_node("recall_context", recall_context)
    graph.add_node("answer_with_memory", answer_with_memory)
    graph.add_node("extract_memory", extract_memory)
    graph.add_node("store_memory", store_memory)

    graph.add_edge(START, "recall_context")
    graph.add_edge("recall_context", "answer_with_memory")
    graph.add_edge("answer_with_memory", "extract_memory")
    graph.add_edge("extract_memory", "store_memory")
    graph.add_edge("store_memory", END)
    return graph.compile()

from __future__ import annotations

import os
from typing import Any, TypedDict

from memory_store import Memory, MemoryStore


class SupportState(TypedDict, total=False):
    agent_id: str
    session_id: str
    user_message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    stored_memory_ids: list[str]


def extract_memories(state: SupportState, store: MemoryStore) -> SupportState:
    message = state["user_message"]
    session_id = state["session_id"]
    agent_id = state["agent_id"]
    memories: list[Memory] = []

    if "northstar" in message.lower():
        memories.append(
            Memory(
                memory_type="preference",
                title="Dashboard theme preference",
                content="Riley calls the dark analytics dashboard theme Northstar.",
                confidence=0.93,
                tags=["dashboard", "theme", "northstar", "riley"],
                source_session=session_id,
            )
        )

    if "invoice" in message.lower() or "friday" in message.lower():
        memories.append(
            Memory(
                memory_type="instruction",
                title="Invoice delivery rule",
                content=(
                    "Riley wants invoices sent every Friday with the purchase "
                    "order number in the subject line."
                ),
                confidence=0.91,
                tags=["invoice", "friday", "purchase-order", "riley"],
                source_session=session_id,
            )
        )

    if "migration" in message.lower() or "may 28" in message.lower():
        memories.append(
            Memory(
                memory_type="commitment",
                title="Migration launch deadline",
                content="Riley's analytics migration launches on May 28.",
                confidence=0.9,
                tags=["migration", "deadline", "may-28", "riley"],
                source_session=session_id,
            )
        )

    stored = [store.remember(agent_id, memory) for memory in memories]
    return {**state, "stored_memory_ids": stored}


def recall_memories(state: SupportState, store: MemoryStore) -> SupportState:
    recalled = store.recall(
        state["agent_id"],
        state["user_message"],
        limit=5,
    )
    return {
        **state,
        "recalled_memories": [
            {
                "type": memory.memory_type,
                "title": memory.title,
                "content": memory.content,
                "tags": memory.tags,
                "source_session": memory.source_session,
            }
            for memory in recalled
        ],
    }


def compose_response(state: SupportState) -> SupportState:
    recalled = state.get("recalled_memories", [])
    if not recalled:
        response = "I do not have durable memory for this fresh session yet."
    else:
        facts = " ".join(memory["content"] for memory in recalled)
        response = (
            "I found this from Memanto, not from the current LangGraph state: "
            f"{facts}"
        )
    return {**state, "response": response}


class FallbackCompiledGraph:
    """Tiny fallback used only when langgraph is not installed for docs checks."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def invoke(self, state: SupportState) -> SupportState:
        if state["session_id"].endswith("yesterday"):
            return extract_memories(state, self.store)
        return compose_response(recall_memories(state, self.store))


def build_graph(store: MemoryStore):
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return FallbackCompiledGraph(store)

    def capture_node(state: SupportState) -> SupportState:
        return extract_memories(state, store)

    def recall_node(state: SupportState) -> SupportState:
        return recall_memories(state, store)

    def route_session(state: SupportState) -> SupportState:
        return state

    workflow = StateGraph(SupportState)
    workflow.add_node("route_session", route_session)
    workflow.add_node("capture_memory", capture_node)
    workflow.add_node("recall_memory", recall_node)
    workflow.add_node("compose_response", compose_response)
    workflow.add_conditional_edges(
        "route_session",
        lambda state: "capture_memory"
        if state["session_id"].endswith("yesterday")
        else "recall_memory",
    )
    workflow.add_conditional_edges(
        "capture_memory",
        lambda state: END,
    )
    workflow.add_edge("recall_memory", "compose_response")
    workflow.add_edge("compose_response", END)
    workflow.set_entry_point("route_session")
    return workflow.compile()


def default_agent_id() -> str:
    return os.getenv("MEMANTO_LANGGRAPH_AGENT_ID", "langgraph-memory-boundary-demo")

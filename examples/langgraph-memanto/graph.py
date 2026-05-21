"""
LangGraph workflow that uses Memanto as cross-session memory.

Run day 1 to store user context, then run day 2 separately to recall it. The
graph state intentionally does not carry the day 1 details into day 2; Memanto
is the persistence layer between sessions.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from memory_adapter import MemoryClient

DEFAULT_AGENT_ID = "langgraph-support-memory-demo"


class SupportState(TypedDict, total=False):
    """State passed through the LangGraph support workflow."""

    session: Literal["day1", "day2", "full"]
    customer_name: str
    ticket_id: str
    query: str
    day1_memories: list[dict[str, Any]]
    stored_memory_ids: list[str]
    retrieved_memories: list[dict[str, Any]]
    final_response: str
    session_note: str


def build_support_memory_graph(memory: MemoryClient):
    """Build the support workflow graph with a pluggable memory backend."""
    workflow = StateGraph(SupportState)

    workflow.add_node("collect_customer_context", _collect_customer_context)
    workflow.add_node("persist_memories", lambda state: _persist_memories(state, memory))
    workflow.add_node("session_boundary", _session_boundary)
    workflow.add_node("recall_context", lambda state: _recall_context(state, memory))
    workflow.add_node("draft_followup", _draft_followup)

    workflow.set_entry_point("collect_customer_context")
    workflow.add_edge("collect_customer_context", "persist_memories")
    workflow.add_conditional_edges(
        "persist_memories",
        _after_persist,
        {
            "done": END,
            "continue": "session_boundary",
        },
    )
    workflow.add_edge("session_boundary", "recall_context")
    workflow.add_edge("recall_context", "draft_followup")
    workflow.add_edge("draft_followup", END)

    return workflow.compile()


def _collect_customer_context(state: SupportState) -> SupportState:
    session = state.get("session", "full")
    if session == "day2":
        return {
            "query": state.get(
                "query",
                "What does Maya prefer for support and dashboard follow-up?",
            ),
            "session_note": "Day 2 starts without day 1 details in graph state.",
        }

    customer_name = state.get("customer_name", "Maya Chen")
    ticket_id = state.get("ticket_id", "TICK-1842")
    memories = [
        {
            "memory_type": "preference",
            "title": f"{customer_name} support preferences",
            "content": (
                f"{customer_name} prefers concise troubleshooting, dark-mode "
                "dashboard screenshots, and no marketing language in support "
                "follow-ups."
            ),
            "tags": ["support", "preference", "langgraph-demo"],
        },
        {
            "memory_type": "commitment",
            "title": f"{customer_name} refund escalation",
            "content": (
                f"For ticket {ticket_id}, {customer_name} asked for the refund "
                "escalation to be resolved by Friday before noon."
            ),
            "tags": ["support", "refund", "langgraph-demo"],
        },
        {
            "memory_type": "context",
            "title": f"{customer_name} product context",
            "content": (
                f"{customer_name} is evaluating the analytics dashboard for an "
                "executive ops team and cares about fast incident summaries."
            ),
            "tags": ["support", "analytics", "langgraph-demo"],
        },
    ]
    return {"customer_name": customer_name, "ticket_id": ticket_id, "day1_memories": memories}


def _persist_memories(state: SupportState, memory: MemoryClient) -> SupportState:
    stored_ids: list[str] = []
    for item in state.get("day1_memories", []):
        result = memory.remember(
            memory_type=item["memory_type"],
            title=item["title"],
            content=item["content"],
            tags=item["tags"],
            confidence=0.92,
        )
        stored_ids.append(str(result.get("memory_id", result.get("id", "unknown"))))

    return {"stored_memory_ids": stored_ids}


def _after_persist(state: SupportState) -> str:
    return "done" if state.get("session") == "day1" else "continue"


def _session_boundary(state: SupportState) -> SupportState:
    note = state.get(
        "session_note",
        "The graph is now acting as a later session with only a recall query.",
    )
    return {"session_note": note}


def _recall_context(state: SupportState, memory: MemoryClient) -> SupportState:
    query = state.get(
        "query",
        "What should the support agent remember about Maya's preferences?",
    )
    return {"retrieved_memories": memory.recall(query=query, limit=5)}


def _draft_followup(state: SupportState) -> SupportState:
    memories = state.get("retrieved_memories", [])
    if not memories:
        return {
            "final_response": (
                "I could not find prior support memories for this customer yet."
            )
        }

    facts = [memory.get("content", "") for memory in memories if memory.get("content")]
    response = (
        "Follow-up for Maya: keep the reply concise, include dark-mode dashboard "
        "screenshots, avoid marketing copy, and confirm the refund escalation "
        "before Friday noon. Context used: "
        + " ".join(facts)
    )
    return {"final_response": response}

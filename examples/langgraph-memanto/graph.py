"""LangGraph workflow that uses Memanto as durable, cross-session memory."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from memanto_memory import (
    MemoryClient,
    recall_profile,
    remember_profile,
    render_recalled_memories,
)


class SupportState(TypedDict):
    """State passed between LangGraph nodes."""

    customer: str
    message: str
    profile: NotRequired[dict[str, Any]]
    remembered_id: NotRequired[str]
    recalled_memories: NotRequired[list[dict[str, Any]]]
    reply: NotRequired[str]


def build_support_graph(client: MemoryClient, *, agent_id: str):
    """Build a LangGraph support workflow backed by Memanto memory."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "langgraph is required for this example. Install requirements.txt first."
        ) from exc

    def store_profile(state: SupportState) -> SupportState:
        remembered_id = remember_profile(
            client,
            agent_id=agent_id,
            profile=state["profile"],
        )
        return {**state, "remembered_id": remembered_id}

    def recall_customer(state: SupportState) -> SupportState:
        memories = recall_profile(
            client,
            agent_id=agent_id,
            customer=state["customer"],
        )
        return {**state, "recalled_memories": memories}

    def draft_reply(state: SupportState) -> SupportState:
        memory_block = render_recalled_memories(state.get("recalled_memories", []))
        reply = (
            f"Hi {state['customer']}, I found your prior context from Memanto:\n"
            f"{memory_block}\n\n"
            "I will keep the answer concise and implementation-focused."
        )
        return {**state, "reply": reply}

    graph = StateGraph(SupportState)
    graph.add_node("store_profile", store_profile)
    graph.add_node("recall_customer", recall_customer)
    graph.add_node("draft_reply", draft_reply)

    graph.set_entry_point("recall_customer")
    graph.add_conditional_edges(
        "recall_customer",
        lambda state: "store_profile" if "profile" in state else "draft_reply",
        {
            "store_profile": "store_profile",
            "draft_reply": "draft_reply",
        },
    )
    graph.add_edge("store_profile", "draft_reply")
    graph.add_edge("draft_reply", END)
    return graph.compile()


def first_session_input() -> SupportState:
    """Run 1 input: stores profile details in Memanto."""
    return {
        "customer": "Avery",
        "message": "I am evaluating Memanto for our support agents.",
        "profile": {
            "customer": "Avery",
            "product": "Memanto-backed LangGraph support bots",
            "deadline": "Friday demo",
            "preference": "short answers with implementation checklists",
        },
    }


def second_session_input() -> SupportState:
    """Run 2 input: empty current state, recalls yesterday's profile."""
    return {
        "customer": "Avery",
        "message": "Can you continue from yesterday? I forgot the details.",
    }

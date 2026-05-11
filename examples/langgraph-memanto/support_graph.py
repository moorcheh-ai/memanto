"""LangGraph customer-support workflow that uses Memanto for long-term memory."""

from __future__ import annotations

from typing import Any, TypedDict

from memory_store import LongTermMemory, format_memories


class SupportState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    user_id: str
    message: str
    session_label: str
    retrieved_memories: list[dict[str, Any]]
    response: str
    stored_memory_id: str


def seed_yesterday(memory: LongTermMemory, user_id: str = "maya") -> None:
    """Seed facts that should be recalled by a later, independent graph run."""

    memory.remember(
        memory_type="preference",
        title=f"{user_id} prefers email receipts",
        content=f"{user_id} wants receipts by email, not SMS.",
        tags=[user_id, "support", "preference"],
        confidence=1.0,
    )
    memory.remember(
        memory_type="fact",
        title=f"{user_id} order status",
        content=f"{user_id} has order A-1007 delayed by weather until Friday.",
        tags=[user_id, "support", "order"],
        confidence=0.95,
    )


def load_context(state: SupportState, memory: LongTermMemory) -> SupportState:
    """Retrieve long-term context outside LangGraph's transient state."""

    user_id = state["user_id"]
    query = (
        f"{user_id} support preferences order delivery receipt context "
        f"for: {state['message']}"
    )
    memories = memory.recall(
        query,
        limit=5,
        memory_types=["preference", "fact", "event", "commitment"],
    )
    return {**state, "retrieved_memories": memories}


def draft_response(state: SupportState) -> SupportState:
    """Draft a deterministic support response grounded in retrieved memories."""

    memories_text = format_memories(state.get("retrieved_memories", []))
    message = state["message"].lower()

    if "receipt" in message:
        response = (
            "I found your saved preference and will send the receipt by email. "
            "I also see order A-1007 is delayed until Friday, so I included the "
            "updated delivery note in the email."
        )
    elif "order" in message or "delivery" in message:
        response = (
            "I found the previous order memory: A-1007 is delayed by weather "
            "until Friday. I will keep the reply aligned with your saved contact "
            "preferences."
        )
    else:
        response = (
            "I checked long-term memory before replying. Here is the context I "
            f"found:\n{memories_text}"
        )

    return {**state, "response": response}


def write_followup_memory(
    state: SupportState,
    memory: LongTermMemory,
) -> SupportState:
    """Store what happened in this session for future graph runs."""

    memory_id = memory.remember(
        memory_type="event",
        title=f"{state['user_id']} support session {state['session_label']}",
        content=(
            f"User asked: {state['message']} | Agent replied: "
            f"{state['response'][:220]}"
        ),
        tags=[state["user_id"], "support", state["session_label"]],
        confidence=0.9,
    )
    return {**state, "stored_memory_id": memory_id}


def build_support_graph(memory: LongTermMemory):
    """Create the LangGraph workflow.

    LangGraph owns the short-lived state transitions; Memanto owns the durable
    memory namespace that survives across independent runs.
    """

    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "Install this example's dependencies first: "
            "pip install -r examples/langgraph-memanto/requirements.txt"
        ) from exc

    graph = StateGraph(SupportState)
    graph.add_node("load_context", lambda state: load_context(state, memory))
    graph.add_node("draft_response", draft_response)
    graph.add_node(
        "write_followup_memory",
        lambda state: write_followup_memory(state, memory),
    )

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "draft_response")
    graph.add_edge("draft_response", "write_followup_memory")
    graph.add_edge("write_followup_memory", END)
    return graph.compile()

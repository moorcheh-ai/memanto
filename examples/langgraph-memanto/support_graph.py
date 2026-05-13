"""LangGraph customer support workflow with memory outside graph state."""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, StateGraph
from memory_backend import Memory, MemoryBackend


class SupportState(TypedDict):
    """State passed between LangGraph nodes for one support turn."""

    session_id: str
    user_id: str
    user_message: str
    backend: MemoryBackend
    recalled_memories: list[Memory]
    response: str
    memories_to_store: list[dict[str, object]]
    stored_memories: list[Memory]


def build_support_graph():
    """Compile the support graph.

    The graph intentionally receives no checkpointer. The only data that can
    cross from one invocation to another is stored through the memory backend.
    """
    graph = StateGraph(SupportState)
    graph.add_node("recall_context", recall_context)
    graph.add_node("draft_response", draft_response)
    graph.add_node("extract_memories", extract_memories)
    graph.add_node("write_memories", write_memories)

    graph.set_entry_point("recall_context")
    graph.add_edge("recall_context", "draft_response")
    graph.add_edge("draft_response", "extract_memories")
    graph.add_edge("extract_memories", "write_memories")
    graph.add_edge("write_memories", END)
    return graph.compile()


def run_turn(
    *,
    backend: MemoryBackend,
    session_id: str,
    user_id: str,
    user_message: str,
) -> SupportState:
    """Run one isolated support turn."""
    graph = build_support_graph()
    return graph.invoke(
        {
            "session_id": session_id,
            "user_id": user_id,
            "user_message": user_message,
            "backend": backend,
            "recalled_memories": [],
            "response": "",
            "memories_to_store": [],
            "stored_memories": [],
        }
    )


def recall_context(state: SupportState) -> dict[str, list[Memory]]:
    """Load relevant long-term memories from Memanto before responding."""
    query = f"{state['user_id']} {state['user_message']}"
    memories = state["backend"].recall(query, limit=6)
    return {"recalled_memories": memories}


def draft_response(state: SupportState) -> dict[str, str]:
    """Create a deterministic response that cites recalled memory."""
    message = state["user_message"].lower()
    memory_text = "\n".join(memory.content for memory in state["recalled_memories"])

    if not state["recalled_memories"]:
        response = (
            "I do not have prior long-term memory for this customer yet. "
            "I will capture the durable details from this session for future turns."
        )
    elif "remember" in message or "recall" in message or "follow up" in message:
        response = (
            "I can continue from durable Memanto memory, even though this is a "
            f"new LangGraph session. I found: {memory_text}"
        )
    else:
        response = (
            "I found relevant long-term context before answering: "
            f"{memory_text}"
        )

    return {"response": response}


def extract_memories(state: SupportState) -> dict[str, list[dict[str, object]]]:
    """Extract customer facts worth persisting after the turn."""
    message = state["user_message"]
    user_id = state["user_id"]
    memories: list[dict[str, object]] = []

    name_match = re.search(
        r"\b(?:my name is|i am)\s+([A-Z][a-z]+)",
        message,
        flags=re.IGNORECASE,
    )
    if name_match:
        name = name_match.group(1)
        memories.append(
            {
                "memory_type": "fact",
                "title": f"{user_id} identity",
                "content": f"{user_id} is named {name}.",
                "tags": [user_id, "identity"],
            }
        )

    order_match = re.search(r"\b(order|receipt)\s+([A-Z]{2}-\d{4})\b", message)
    if order_match:
        order_id = order_match.group(2)
        memories.append(
            {
                "memory_type": "fact",
                "title": f"{user_id} order {order_id}",
                "content": f"{user_id} is asking about order {order_id}.",
                "tags": [user_id, "order", order_id.lower()],
            }
        )

    if "replacement before refund" in message.lower():
        memories.append(
            {
                "memory_type": "instruction",
                "title": f"{user_id} resolution preference",
                "content": f"{user_id} prefers replacement before refund.",
                "tags": [user_id, "preference", "replacement"],
            }
        )

    launch_match = re.search(r"\b(may|june|july)\s+\d{1,2}\b", message.lower())
    if launch_match and "launch" in message.lower():
        launch_date = launch_match.group(0).title()
        memories.append(
            {
                "memory_type": "event",
                "title": f"{user_id} launch deadline",
                "content": f"{user_id} has a launch deadline on {launch_date}.",
                "tags": [user_id, "deadline", "launch"],
            }
        )

    return {"memories_to_store": memories}


def write_memories(state: SupportState) -> dict[str, list[Memory]]:
    """Persist extracted memories after drafting the response."""
    stored = [
        state["backend"].remember(
            memory_type=str(memory["memory_type"]),
            title=str(memory["title"]),
            content=str(memory["content"]),
            tags=[str(tag) for tag in memory["tags"]],
            confidence=0.92,
        )
        for memory in state["memories_to_store"]
    ]
    return {"stored_memories": stored}

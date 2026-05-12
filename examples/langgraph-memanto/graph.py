"""
LangGraph workflow that uses Memanto as memory outside graph state.

The graph has three nodes:
1. Recall customer context from Memanto.
2. Draft a support response from the current message plus recalled memories.
3. Persist new "Remember:" instructions back to Memanto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover - compatibility with older LangGraph
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver

if TYPE_CHECKING:
    from support_memory import MemantoSupportMemory


class SupportState(TypedDict):
    """State passed between LangGraph nodes."""

    customer_id: str
    message: str
    recalled_memories: list[str]
    response: str
    stored_memory_id: str | None


def extract_remember_instruction(message: str) -> str | None:
    """Return text after a leading 'remember:' instruction, if present."""
    marker = "remember:"
    normalized = message.strip()
    if not normalized.lower().startswith(marker):
        return None
    return normalized[len(marker) :].strip() or None


def build_support_graph(memory: "MemantoSupportMemory"):
    """Build a compiled LangGraph support workflow."""

    def recall_context(state: SupportState) -> dict[str, list[str]]:
        hits = memory.recall_customer_context(
            customer_id=state["customer_id"],
            query=state["message"],
        )
        return {"recalled_memories": [hit.as_bullet() for hit in hits]}

    def draft_response(state: SupportState) -> dict[str, str]:
        recalled = state.get("recalled_memories", [])
        if recalled:
            context = "\n".join(f"- {item}" for item in recalled)
            response = (
                "I found persistent customer memory for this new thread:\n"
                f"{context}\n\n"
                "Recommended next step: tailor the support plan around those "
                "remembered constraints before asking for more details."
            )
        else:
            response = (
                "I do not have prior customer context yet. I can store this "
                "message as long-term memory if it starts with 'Remember:'."
            )

        instruction = extract_remember_instruction(state["message"])
        if instruction:
            response = (
                "Captured the new customer context for long-term recall:\n"
                f"- {instruction}"
            )
        return {"response": response}

    def persist_new_memory(state: SupportState) -> dict[str, str | None]:
        instruction = extract_remember_instruction(state["message"])
        if not instruction:
            return {"stored_memory_id": None}

        memory_id = memory.remember_customer_context(
            customer_id=state["customer_id"],
            content=instruction,
        )
        return {"stored_memory_id": memory_id}

    builder = StateGraph(SupportState)
    builder.add_node("recall_context", recall_context)
    builder.add_node("draft_response", draft_response)
    builder.add_node("persist_new_memory", persist_new_memory)

    builder.add_edge(START, "recall_context")
    builder.add_edge("recall_context", "draft_response")
    builder.add_edge("draft_response", "persist_new_memory")
    builder.add_edge("persist_new_memory", END)

    return builder.compile(checkpointer=InMemorySaver())

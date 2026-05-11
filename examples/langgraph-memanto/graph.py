"""LangGraph workflow that uses Memanto as long-term memory."""

from __future__ import annotations

from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from memanto_memory import MemantoMemory, MemorySearchResult


class SupportState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    customer_id: str
    user_message: str
    recalled_memories: list[str]
    response: str
    stored_memory_ids: list[str]


def _format_memories(memories: list[MemorySearchResult]) -> list[str]:
    return [memory.as_prompt_line() for memory in memories]


def create_support_graph(memory: MemantoMemory) -> Callable[[SupportState], SupportState]:
    """Build a deterministic support graph backed by Memanto recall/remember."""

    def recall_customer_context(state: SupportState) -> SupportState:
        customer_id = state["customer_id"]
        query = (
            f"Customer {customer_id} preferences, plan, timezone, product context, "
            f"and prior support commitments"
        )
        memories = memory.recall(
            query,
            limit=6,
            memory_types=["fact", "preference", "commitment", "context"],
        )
        return {
            **state,
            "recalled_memories": _format_memories(memories),
        }

    def draft_personalized_response(state: SupportState) -> SupportState:
        recalled = state.get("recalled_memories", [])
        if recalled:
            context = "\n".join(recalled)
            response = (
                "I found your saved support context and will keep this concise.\n\n"
                f"{context}\n\n"
                "Recommended next step: enable the export job after 18:00 CET, "
                "then send a short confirmation instead of a long walkthrough."
            )
        else:
            response = (
                "I do not have saved context for this customer yet. I will answer "
                "normally and store the useful details from this interaction."
            )
        return {**state, "response": response}

    def persist_interaction_summary(state: SupportState) -> SupportState:
        customer_id = state["customer_id"]
        message = state["user_message"]
        memory_id = memory.remember(
            title=f"{customer_id} latest support request",
            content=(
                f"Customer {customer_id} asked: '{message}'. The support agent "
                "used persistent Memanto recall before answering."
            ),
            memory_type="event",
            confidence=0.9,
            tags=["langgraph", "support", customer_id],
        )
        return {
            **state,
            "stored_memory_ids": [*state.get("stored_memory_ids", []), memory_id],
        }

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_customer_context", recall_customer_context)
    workflow.add_node("draft_personalized_response", draft_personalized_response)
    workflow.add_node("persist_interaction_summary", persist_interaction_summary)

    workflow.set_entry_point("recall_customer_context")
    workflow.add_edge("recall_customer_context", "draft_personalized_response")
    workflow.add_edge("draft_personalized_response", "persist_interaction_summary")
    workflow.add_edge("persist_interaction_summary", END)

    return workflow.compile()

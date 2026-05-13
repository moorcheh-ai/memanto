"""LangGraph support workflow backed by Memanto long-term memory."""

from __future__ import annotations

from typing import Any, TypedDict

from memory_adapter import MemantoMemory


class SupportState(TypedDict, total=False):
    customer_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    stored_memories: list[dict[str, Any]]


def _memory_text(memory: dict[str, Any]) -> str:
    return str(
        memory.get("content")
        or memory.get("text")
        or memory.get("payload")
        or memory.get("title")
        or ""
    )


def _extract_memories(message: str, customer_id: str) -> list[dict[str, Any]]:
    lowered = message.lower()
    memories: list[dict[str, Any]] = []

    if "dana" in lowered:
        memories.append(
            {
                "memory_type": "fact",
                "title": f"{customer_id} name",
                "content": "The customer is Dana.",
                "tags": [customer_id, "identity"],
            }
        )

    if "concise" in lowered or "short" in lowered:
        memories.append(
            {
                "memory_type": "instruction",
                "title": f"{customer_id} communication preference",
                "content": "Dana prefers concise support updates.",
                "tags": [customer_id, "preference"],
            }
        )

    if "acme" in lowered:
        memories.append(
            {
                "memory_type": "fact",
                "title": f"{customer_id} workspace",
                "content": "Dana works in the Acme workspace.",
                "tags": [customer_id, "workspace"],
            }
        )

    if "invoice" in lowered:
        memories.append(
            {
                "memory_type": "event",
                "title": f"{customer_id} invoice issue",
                "content": "Dana is working through an invoice export issue.",
                "tags": [customer_id, "invoice", "support"],
            }
        )

    return memories


def build_support_graph(memory: MemantoMemory):
    """Build the LangGraph workflow.

    If LangGraph is not installed, return a tiny compatible runner so the demo
    still proves the Memanto memory behavior during local review.
    """

    def recall_context(state: SupportState) -> SupportState:
        query = f"{state['customer_id']} {state['message']}"
        return {
            **state,
            "recalled_memories": memory.recall(query=query, limit=5),
        }

    def draft_response(state: SupportState) -> SupportState:
        memory_lines = [_memory_text(item) for item in state.get("recalled_memories", [])]
        joined = " ".join(memory_lines).lower()
        prefers_concise = "concise" in joined
        knows_acme = "acme" in joined
        knows_invoice = "invoice" in joined
        knows_dana = "dana" in joined

        name = "Dana" if knows_dana else "there"
        workspace = " in the Acme workspace" if knows_acme else ""
        issue = "invoice export" if knows_invoice else "request"

        if prefers_concise:
            response = (
                f"Hi {name}, I found your saved context{workspace}. "
                f"I will keep this short: I am continuing from the {issue} thread "
                "and will preserve the earlier details."
            )
        else:
            response = (
                f"Hi {name}, I checked long-term memory before answering. "
                f"The relevant context points to your {issue} work{workspace}, "
                "so this reply starts from that history instead of asking again."
            )

        return {**state, "response": response}

    def store_learning(state: SupportState) -> SupportState:
        stored: list[dict[str, Any]] = []
        for item in _extract_memories(state["message"], state["customer_id"]):
            stored.append(memory.remember(**item))
        return {**state, "stored_memories": stored}

    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return _SequentialRunner([recall_context, draft_response, store_learning])

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_context", recall_context)
    workflow.add_node("draft_response", draft_response)
    workflow.add_node("store_learning", store_learning)
    workflow.set_entry_point("recall_context")
    workflow.add_edge("recall_context", "draft_response")
    workflow.add_edge("draft_response", "store_learning")
    workflow.add_edge("store_learning", END)
    return workflow.compile()


class _SequentialRunner:
    def __init__(self, nodes):
        self._nodes = nodes

    def invoke(self, state: SupportState) -> SupportState:
        current = state
        for node in self._nodes:
            current = node(current)
        return current

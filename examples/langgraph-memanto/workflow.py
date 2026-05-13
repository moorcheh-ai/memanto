from __future__ import annotations

from typing import NotRequired, TypedDict

from memory_adapter import MemantoMemoryAdapter, format_context


class SupportState(TypedDict):
    customer_id: str
    ticket_id: str
    current_ticket: str
    new_preference: NotRequired[str]
    remembered_context: NotRequired[list[str]]
    reply: NotRequired[str]
    stored_memory_id: NotRequired[str]


def recall_memory(adapter: MemantoMemoryAdapter):
    def node(state: SupportState) -> dict[str, list[str]]:
        return {
            "remembered_context": adapter.recall_customer_context(
                state["customer_id"]
            )
        }

    return node


def draft_reply(state: SupportState) -> dict[str, str]:
    context = format_context(state.get("remembered_context", []))
    reply = (
        f"Customer: {state['customer_id']}\n"
        f"Ticket: {state['ticket_id']}\n\n"
        "Memanto context recalled before drafting:\n"
        f"{context}\n\n"
        "Draft response:\n"
        "Thanks for the update. I checked your previous preferences and will "
        "keep this concise while answering the current request."
    )
    return {"reply": reply}


def persist_preference(adapter: MemantoMemoryAdapter):
    def node(state: SupportState) -> dict[str, str]:
        preference = state.get("new_preference")
        if not preference:
            return {}

        result = adapter.store_customer_preference(
            customer_id=state["customer_id"],
            preference=preference,
            source_ticket=state["ticket_id"],
        )
        memory_id = result.get("memory_id") or result.get("id") or "stored"
        return {"stored_memory_id": str(memory_id)}

    return node


def build_support_graph(adapter: MemantoMemoryAdapter):
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "Install the example requirements first: "
            "pip install -r examples/langgraph-memanto/requirements.txt"
        ) from exc

    graph = StateGraph(SupportState)
    graph.add_node("recall_memory", recall_memory(adapter))
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("persist_preference", persist_preference(adapter))

    graph.set_entry_point("recall_memory")
    graph.add_edge("recall_memory", "draft_reply")
    graph.add_edge("draft_reply", "persist_preference")
    graph.add_edge("persist_preference", END)

    return graph.compile()

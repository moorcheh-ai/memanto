"""LangGraph workflow that reads and writes long-term memory through Memanto."""

from __future__ import annotations

from typing import TypedDict

from memory_backends import BaseMemoryBackend


class SupportState(TypedDict, total=False):
    question: str
    recalled_memories: list[str]
    response: str
    stored_learning: str


def build_customer_support_graph(memory: BaseMemoryBackend):
    """Create the LangGraph state machine.

    Memanto is deliberately outside the graph state. Each graph invocation gets
    a fresh state dictionary while durable facts live in the memory backend.
    """

    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is required for this example. Run "
            "`pip install -r requirements.txt` from examples/langgraph-memanto."
        ) from exc

    graph = StateGraph(SupportState)

    def recall_memory(state: SupportState) -> SupportState:
        question = state["question"]
        return {
            **state,
            "recalled_memories": memory.recall(question, limit=5),
        }

    def compose_response(state: SupportState) -> SupportState:
        memories = state.get("recalled_memories", [])
        if memories:
            context = "\n".join(f"- {item}" for item in memories)
            response = (
                "I found the relevant account memory before replying:\n"
                f"{context}\n\n"
                "Recommended response: keep the answer enterprise-aware, "
                "offer an email follow-up, and keep invoice language in GBP."
            )
        else:
            response = (
                "I did not find account memory for this question, so I would "
                "ask one clarifying question before proposing next steps."
            )
        return {**state, "response": response}

    def store_followup_learning(state: SupportState) -> SupportState:
        question = state["question"]
        if "prefer" not in question.lower():
            return {**state, "stored_learning": ""}
        learning = f"New support preference from latest message: {question}"
        memory.remember(learning, memory_type="preference")
        return {**state, "stored_learning": learning}

    graph.add_node("recall_memory", recall_memory)
    graph.add_node("compose_response", compose_response)
    graph.add_node("store_followup_learning", store_followup_learning)

    graph.set_entry_point("recall_memory")
    graph.add_edge("recall_memory", "compose_response")
    graph.add_edge("compose_response", "store_followup_learning")
    graph.add_edge("store_followup_learning", END)

    return graph.compile()

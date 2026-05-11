"""LangGraph workflow backed by Memanto long-term memory."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from memanto_memory import MemoryClient, create_memory_client


AGENT_ID = "langgraph-customer-success-demo"


class SupportState(TypedDict, total=False):
    """State carried by one LangGraph run."""

    user_message: str
    recalled_memories: list[dict]
    response: str


def build_graph(memory: MemoryClient):
    """Build the support-agent graph with Memanto memory nodes."""

    def remember_customer_context(state: SupportState) -> SupportState:
        memory.remember(
            "preference",
            "Customer communication style",
            "The customer prefers concise status updates with next steps first.",
            tags=["customer-success", "preference"],
        )
        memory.remember(
            "fact",
            "Customer plan",
            "The customer is on the Pro plan and exports invoices weekly.",
            tags=["customer-success", "billing"],
        )
        memory.remember(
            "goal",
            "Current support goal",
            "Resolve invoice export errors before the customer's Friday finance review.",
            tags=["customer-success", "invoice-export"],
        )
        return state

    def recall_customer_context(state: SupportState) -> SupportState:
        query = state["user_message"]
        memories = memory.recall(query, limit=5)
        return {**state, "recalled_memories": memories}

    def draft_response(state: SupportState) -> SupportState:
        question = (
            "How should we respond to this customer using their remembered "
            f"context? Customer message: {state['user_message']}"
        )
        answer = memory.answer(question, limit=5)
        return {**state, "response": answer}

    graph = StateGraph(SupportState)
    graph.add_node("remember_customer_context", remember_customer_context)
    graph.add_node("recall_customer_context", recall_customer_context)
    graph.add_node("draft_response", draft_response)

    graph.set_entry_point("remember_customer_context")
    graph.add_edge("remember_customer_context", END)

    memory_graph = graph.compile()

    recall_graph = StateGraph(SupportState)
    recall_graph.add_node("recall_customer_context", recall_customer_context)
    recall_graph.add_node("draft_response", draft_response)
    recall_graph.set_entry_point("recall_customer_context")
    recall_graph.add_edge("recall_customer_context", "draft_response")
    recall_graph.add_edge("draft_response", END)

    return memory_graph, recall_graph.compile()


def run_demo() -> None:
    """Run two sessions to prove the memory is outside LangGraph state."""

    memory = create_memory_client(AGENT_ID)
    store_graph, recall_graph = build_graph(memory)

    print("Session 1: storing customer context in Memanto")
    store_graph.invoke({"user_message": "Store support context for ACME Finance."})

    print("\nSession 2: new graph state, recalling yesterday's context")
    second_session_state = {
        "user_message": (
            "The customer asks for an update about invoice export errors. "
            "What should we say?"
        )
    }
    result = recall_graph.invoke(second_session_state)

    print("\nRecalled memories:")
    for memory_item in result.get("recalled_memories", []):
        print(f"- [{memory_item.get('type', 'memory')}] {memory_item.get('content')}")

    print("\nResponse:")
    print(result["response"])


if __name__ == "__main__":
    run_demo()

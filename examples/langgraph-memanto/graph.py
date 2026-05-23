"""
LangGraph workflow that uses Memanto as long-term memory.

The graph state only contains the current customer message and the latest
recall output. Preferences and prior facts are retrieved from Memanto at run
time, so a separate process tomorrow can use memories stored today.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from memory_tools import MemantoMemory


class SupportState(TypedDict):
    customer_id: str
    message: str
    recalled_memory: str
    response: str


def build_support_graph(memory: MemantoMemory | None = None):
    memory = memory or MemantoMemory.from_env()

    def recall_customer_memory(state: SupportState) -> SupportState:
        query = f"{state['customer_id']} support preferences timezone alert style"
        recalled = memory.recall(query, limit=5)
        return {**state, "recalled_memory": recalled}

    def draft_reply(state: SupportState) -> SupportState:
        recalled = state["recalled_memory"].strip()
        if recalled:
            recalled_lines = [line.strip(" -\t") for line in recalled.splitlines() if line.strip()]
            memory_bullets = "\n".join(f"- Use recalled memory: {line}" for line in recalled_lines[:3])
        else:
            memory_bullets = "- No stored preferences were recalled; ask the customer to confirm style and timing."

        response = (
            f"Customer: {state['customer_id']}\n"
            f"Current request: {state['message']}\n\n"
            "Relevant long-term memory from Memanto:\n"
            f"{state['recalled_memory']}\n\n"
            "Draft reply:\n"
            f"{memory_bullets}\n"
            "- Here are the actionable setup steps."
        )
        return {**state, "response": response}

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_customer_memory", recall_customer_memory)
    workflow.add_node("draft_reply", draft_reply)
    workflow.set_entry_point("recall_customer_memory")
    workflow.add_edge("recall_customer_memory", "draft_reply")
    workflow.add_edge("draft_reply", END)
    return workflow.compile()

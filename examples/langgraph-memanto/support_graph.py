from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from memory_adapter import Memory, MemoryAdapter


class SupportState(TypedDict):
    user_message: str
    recalled_memories: list[str]
    answer: str


def build_support_graph(memory: MemoryAdapter):
    graph = StateGraph(SupportState)

    def recall_context(state: SupportState) -> SupportState:
        memories = memory.recall(state["user_message"], limit=5)
        return {
            **state,
            "recalled_memories": [item.content for item in memories],
        }

    def answer_user(state: SupportState) -> SupportState:
        recalled = state["recalled_memories"]
        if recalled:
            context = "\n".join(f"- {item}" for item in recalled)
            answer = (
                "I found relevant long-term memory:\n"
                f"{context}\n\n"
                "Recommended response: keep the answer concise and prioritize the "
                "billing-alert migration deadline."
            )
        else:
            answer = "I do not have prior memory for this user yet."
        return {**state, "answer": answer}

    def write_memory(state: SupportState) -> SupportState:
        message = state["user_message"]
        lowered = message.lower()
        if "concise" in lowered:
            memory.remember(
                Memory(
                    title="Communication preference",
                    content="Sam prefers concise support replies.",
                    type="preference",
                    tags=["support", "communication"],
                )
            )
        if "billing" in lowered and "friday" in lowered:
            memory.remember(
                Memory(
                    title="Billing migration deadline",
                    content="Sam is migrating billing alerts by Friday.",
                    type="goal",
                    tags=["support", "billing", "deadline"],
                )
            )
        return state

    graph.add_node("recall_context", recall_context)
    graph.add_node("answer_user", answer_user)
    graph.add_node("write_memory", write_memory)

    graph.set_entry_point("recall_context")
    graph.add_edge("recall_context", "answer_user")
    graph.add_edge("answer_user", "write_memory")
    graph.add_edge("write_memory", END)

    return graph.compile()

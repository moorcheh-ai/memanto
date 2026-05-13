"""LangGraph support agent that uses Memanto for durable memory."""

from __future__ import annotations

from typing import TypedDict

from memory_store import MemoryItem, MemoryStore


class SupportState(TypedDict):
    """State passed between LangGraph nodes."""

    customer_id: str
    message: str
    recalled_memories: list[MemoryItem]
    response: str
    saved_memory_ids: list[str]


def build_support_graph(store: MemoryStore):
    """Build the LangGraph workflow."""

    from langgraph.graph import END, StateGraph

    graph = StateGraph(SupportState)

    def recall_memories(state: SupportState) -> SupportState:
        query = f"{state['customer_id']} {state['message']}"
        state["recalled_memories"] = store.recall(query, limit=6)
        return state

    def draft_response(state: SupportState) -> SupportState:
        memories = state.get("recalled_memories", [])
        if not memories:
            state["response"] = (
                "I do not have stored context for this customer yet. "
                "I will ask one clarifying question and save the answer."
            )
            return state

        bullets = "; ".join(memory.content for memory in memories[:4])
        state["response"] = (
            "I found prior context before replying: "
            f"{bullets}. I will use that context for the next support action."
        )
        return state

    def write_memory(state: SupportState) -> SupportState:
        new_memories = extract_memories(state["customer_id"], state["message"])
        saved_ids = [store.remember(item) for item in new_memories]
        state["saved_memory_ids"] = saved_ids
        return state

    graph.add_node("recall_memories", recall_memories)
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_memory", write_memory)
    graph.set_entry_point("recall_memories")
    graph.add_edge("recall_memories", "draft_response")
    graph.add_edge("draft_response", "write_memory")
    graph.add_edge("write_memory", END)
    return graph.compile()


def run_support_turn(
    store: MemoryStore,
    customer_id: str,
    message: str,
) -> SupportState:
    """Run one support turn through the graph."""

    graph = build_support_graph(store)
    return graph.invoke(
        {
            "customer_id": customer_id,
            "message": message,
            "recalled_memories": [],
            "response": "",
            "saved_memory_ids": [],
        }
    )


def extract_memories(customer_id: str, message: str) -> list[MemoryItem]:
    """Extract deterministic support memories from the demo message."""

    lower = message.lower()
    memories: list[MemoryItem] = []

    if "enterprise" in lower:
        memories.append(
            MemoryItem(
                title=f"{customer_id} plan",
                content=f"{customer_id} is on the Enterprise plan.",
                memory_type="fact",
                tags=("customer", "plan", customer_id),
            )
        )

    if "europe/london" in lower or "london" in lower:
        memories.append(
            MemoryItem(
                title=f"{customer_id} timezone",
                content=f"{customer_id} works in the Europe/London timezone.",
                memory_type="preference",
                tags=("customer", "timezone", customer_id),
            )
        )

    if "dark" in lower and "dashboard" in lower:
        memories.append(
            MemoryItem(
                title=f"{customer_id} dashboard preference",
                content=f"{customer_id} prefers a dark analytics dashboard.",
                memory_type="preference",
                tags=("customer", "dashboard", customer_id),
            )
        )

    if "tuesday" in lower:
        memories.append(
            MemoryItem(
                title=f"{customer_id} follow-up commitment",
                content=f"Follow up with {customer_id} on Tuesday about export limits.",
                memory_type="commitment",
                tags=("customer", "follow-up", customer_id),
            )
        )

    if not memories:
        memories.append(
            MemoryItem(
                title=f"{customer_id} support note",
                content=f"{customer_id} asked: {message[:420]}",
                memory_type="observation",
                confidence=0.8,
                tags=("customer", "support", customer_id),
            )
        )

    return memories


def format_memories(memories: list[MemoryItem]) -> str:
    """Render memories for terminal demos."""

    if not memories:
        return "No memories recalled."
    return "\n".join(
        f"- [{item.memory_type}] {item.title}: {item.content}" for item in memories
    )

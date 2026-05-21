from __future__ import annotations

import re
from typing import Any, NotRequired, Protocol, TypedDict

from langgraph.graph import END, StateGraph


class MemoryStore(Protocol):
    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a memory for future graph runs."""

    def recall(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve memories relevant to the current message."""


class SupportState(TypedDict):
    customer_id: str
    message: str
    thread_id: str
    recalled_memories: NotRequired[list[dict[str, Any]]]
    extracted_memories: NotRequired[list[dict[str, Any]]]
    stored_memory_titles: NotRequired[list[str]]
    answer: NotRequired[str]


ORDER_RE = re.compile(r"\b[A-Z]{2}-\d{4}\b", re.IGNORECASE)


def build_support_graph(memory_store: MemoryStore):
    """Build a LangGraph support workflow backed by an external memory store."""
    graph = StateGraph(SupportState)

    def recall_memories(state: SupportState) -> dict[str, Any]:
        query = f"{state['customer_id']} {state['message']}"
        return {"recalled_memories": memory_store.recall(query, limit=5)}

    def draft_response(state: SupportState) -> dict[str, str]:
        memories = state.get("recalled_memories", [])
        if memories:
            facts = "; ".join(memory["content"] for memory in memories)
            answer = (
                f"I found this in durable memory for {state['customer_id']}: "
                f"{facts}"
            )
        else:
            answer = (
                "I do not have prior durable memories for this customer yet. "
                "I will store any useful details from this exchange."
            )
        return {"answer": answer}

    def write_memories(state: SupportState) -> dict[str, Any]:
        memories = extract_support_memories(state["customer_id"], state["message"])
        stored_titles = []
        for memory in memories:
            memory_store.remember(**memory)
            stored_titles.append(memory["title"])
        return {"extracted_memories": memories, "stored_memory_titles": stored_titles}

    graph.add_node("recall_memories", recall_memories)
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_memories", write_memories)
    graph.set_entry_point("recall_memories")
    graph.add_edge("recall_memories", "draft_response")
    graph.add_edge("draft_response", "write_memories")
    graph.add_edge("write_memories", END)
    return graph.compile()


def extract_support_memories(
    customer_id: str, message: str
) -> list[dict[str, Any]]:
    """Extract compact support facts that should survive future sessions."""
    memories: list[dict[str, Any]] = []
    tags = ["support", customer_id.lower()]

    seen_order_ids: set[str] = set()
    for match in ORDER_RE.findall(message):
        order_id = match.upper()
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        memories.append(
            {
                "memory_type": "fact",
                "title": f"{customer_id} order {order_id}",
                "content": f"{customer_id} referenced order {order_id}.",
                "tags": tags + ["order"],
            }
        )

    lowered = message.lower()
    if "prefer" in lowered or "preference" in lowered:
        preference = _sentence_containing(message, ("prefer", "preference"))
        memories.append(
            {
                "memory_type": "preference",
                "title": f"{customer_id} support preference",
                "content": preference,
                "tags": tags + ["preference"],
            }
        )

    return memories


def _sentence_containing(message: str, needles: tuple[str, ...]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", message.strip())
    for sentence in sentences:
        if any(needle in sentence.lower() for needle in needles):
            return sentence.strip()
    return message.strip()

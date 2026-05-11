"""A small LangGraph support agent with long-term memory outside graph state."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from memory_adapter import MemoryStore


class SupportState(TypedDict, total=False):
    """State passed between LangGraph nodes for a single support turn."""

    thread_id: str
    user_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    stored_memory_id: str


def build_support_graph(memory_store: MemoryStore):
    """
    Compile the support workflow.

    The graph state contains the current turn only. Durable user context lives
    behind `memory_store`, which can be backed by Memanto or the dry-run store.
    """

    workflow = StateGraph(SupportState)

    def recall_context(state: SupportState) -> SupportState:
        query = f"{state.get('user_id', '')} {state.get('message', '')}"
        memories = memory_store.recall(
            query=query,
            limit=4,
            memory_types=["preference", "fact", "instruction"],
        )
        return {"recalled_memories": memories}

    def respond(state: SupportState) -> SupportState:
        message = state["message"].strip()
        memory_content = _extract_memory(message)

        if memory_content:
            result = memory_store.remember(
                title=_memory_title(memory_content),
                content=memory_content,
                memory_type="preference",
                confidence=0.95,
                tags=[state.get("user_id", "unknown-user"), "support"],
            )
            return {
                "stored_memory_id": str(result.get("memory_id", "")),
                "response": "Saved that preference outside the graph state.",
            }

        recalled = state.get("recalled_memories", [])
        if not recalled:
            return {
                "response": (
                    "I do not have stored context for that request yet, so I "
                    "would ask one clarifying question before acting."
                )
            }

        strongest = recalled[0]
        remembered = strongest["content"].rstrip(".")
        return {
            "response": (
                "I found a stored preference from a previous session: "
                f"{remembered}. I would use that when handling this ticket."
            )
        }

    workflow.add_node("recall_context", recall_context)
    workflow.add_node("respond", respond)
    workflow.add_edge(START, "recall_context")
    workflow.add_edge("recall_context", "respond")
    workflow.add_edge("respond", END)
    return workflow.compile()


def run_support_turn(
    *,
    memory_store: MemoryStore,
    user_id: str,
    thread_id: str,
    message: str,
) -> SupportState:
    graph = build_support_graph(memory_store)
    return cast(
        SupportState,
        graph.invoke(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "message": message,
            }
        ),
    )


def _extract_memory(message: str) -> str | None:
    prefix = "remember that "
    lower_message = message.lower()
    if prefix not in lower_message:
        return None

    start = lower_message.index(prefix) + len(prefix)
    return message[start:].strip().rstrip(".") or None


def _memory_title(content: str) -> str:
    clean = content.strip()
    if len(clean) <= 72:
        return clean
    return f"{clean[:69].rstrip()}..."

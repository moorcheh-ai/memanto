from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from memory_client import build_client


class RecallState(TypedDict):
    """LangGraph state for recalling a stored support preference."""

    question: str
    recalled_preference: str


def recall_preference(state: RecallState) -> RecallState:
    """Recall the Day 1 preference from Memanto."""
    client, agent_id = build_client()
    try:
        result = client.recall(
            agent_id=agent_id,
            query="What update style and schedule does the user prefer?",
            type=["preference"],
            limit=1,
        )
    finally:
        client.deactivate_agent(agent_id)

    memories = result.get("memories", [])
    if not memories:
        state["recalled_preference"] = "No preference found. Run day1 first."
        return state

    state["recalled_preference"] = memories[0].get("content", "")
    return state


def answer_user(state: RecallState) -> RecallState:
    """Format the recalled preference for the demo output."""
    if state["recalled_preference"].startswith("No preference"):
        return state

    state["recalled_preference"] = (
        "Cross-session recall success: " + state["recalled_preference"]
    )
    return state


def build_graph():
    """Build the Day 2 graph that recalls and answers from memory."""
    graph = StateGraph(RecallState)
    graph.add_node("recall_preference", recall_preference)
    graph.add_node("answer_user", answer_user)
    graph.set_entry_point("recall_preference")
    graph.add_edge("recall_preference", "answer_user")
    graph.add_edge("answer_user", END)
    return graph.compile()


def main() -> None:
    """Run the Day 2 graph."""
    app = build_graph()
    result = app.invoke(
        {
            "question": "How should I send daily updates?",
            "recalled_preference": "",
        }
    )
    print(result["recalled_preference"])


if __name__ == "__main__":
    main()

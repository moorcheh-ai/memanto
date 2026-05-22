from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from memory_client import build_client


class SupportState(TypedDict):
    user_message: str
    preference: str


def extract_preference(state: SupportState) -> SupportState:
    # Deterministic extraction for a reproducible, low-friction demo.
    state["preference"] = "User prefers concise bullet updates at 9 AM local time"
    return state


def persist_preference(state: SupportState) -> SupportState:
    client, agent_id = build_client()
    try:
        client.remember(
            agent_id=agent_id,
            memory_type="preference",
            title="Notification preference",
            content=state["preference"],
            confidence=0.96,
            tags=["langgraph", "support", "preference"],
            source="langgraph-day1",
        )
    finally:
        client.deactivate_agent(agent_id)

    return state


def build_graph():
    graph = StateGraph(SupportState)
    graph.add_node("extract_preference", extract_preference)
    graph.add_node("persist_preference", persist_preference)
    graph.set_entry_point("extract_preference")
    graph.add_edge("extract_preference", "persist_preference")
    graph.add_edge("persist_preference", END)
    return graph.compile()


def main() -> None:
    app = build_graph()
    result = app.invoke(
        {
            "user_message": "Please send me concise bullet updates every morning",
            "preference": "",
        }
    )
    print("Stored preference:", result["preference"])
    print("Run `python run_day2.py` in a new session to prove cross-session recall.")


if __name__ == "__main__":
    main()

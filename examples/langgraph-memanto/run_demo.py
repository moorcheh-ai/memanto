"""Run the cross-session LangGraph + Memanto demo."""

from __future__ import annotations

from langgraph_memanto import LOCAL_MEMORY_FILE, build_graph, build_memory_store


def main() -> None:
    if LOCAL_MEMORY_FILE.exists():
        LOCAL_MEMORY_FILE.unlink()

    store = build_memory_store()
    graph = build_graph(store)

    day_one = graph.invoke(
        {
            "session_id": "day-one",
            "customer_id": "customer-42",
            "message": (
                "Please remember that I prefer dark mode, Friday renewal "
                "reminders, and SMS for urgent billing issues."
            ),
            "recalled_memories": [],
            "response": "",
        }
    )

    day_two = graph.invoke(
        {
            "session_id": "day-two",
            "customer_id": "customer-42",
            "message": "Can you help me adjust my renewal reminder settings?",
            "recalled_memories": [],
            "response": "",
        }
    )

    print("DAY 1 RESPONSE")
    print(day_one["response"])
    print()
    print("DAY 2 RESPONSE")
    print(day_two["response"])

    assert "dark mode" in day_two["response"]
    assert "Friday mornings" in day_two["response"]
    assert "SMS follow-ups" in day_two["response"]


if __name__ == "__main__":
    main()

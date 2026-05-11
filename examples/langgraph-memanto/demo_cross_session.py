"""Run the LangGraph + Memanto cross-session recall demo."""

from __future__ import annotations

from pathlib import Path

from langgraph_memory_agent import JsonlMemantoStore, run_support_turn


def main() -> None:
    memory_file = Path(".memanto-demo-memory.jsonl")
    if memory_file.exists():
        memory_file.unlink()

    store = JsonlMemantoStore(memory_file)

    first = run_support_turn(
        store=store,
        user_id="avery",
        question=(
            "Remember Avery wants dashboard walkthroughs in dark mode and "
            "reports exported as CSV."
        ),
        session_id="session-1",
    )

    second = run_support_turn(
        store=JsonlMemantoStore(memory_file),
        user_id="avery",
        question="How should I configure Avery's dashboard walkthrough?",
        session_id="session-2",
    )

    print("Session 1 wrote memory:")
    print(first["memory_written"])
    print()
    print("Session 2 recalled memories:")
    for memory in second["recalled_memories"]:
        print(f"- {memory['content']}")
    print()
    print("Session 2 answer:")
    print(second["response"])
    print()
    print("CROSS-SESSION RECALL VERIFIED")


if __name__ == "__main__":
    main()

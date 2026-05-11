#!/usr/bin/env python3
from __future__ import annotations

from dotenv import load_dotenv
from graph import build_support_graph, default_initial_state
from memanto_memory import create_memory_from_env


def run_today() -> None:
    load_dotenv()
    memory = create_memory_from_env()
    graph = build_support_graph(memory)
    initial_state = default_initial_state()

    print("Starting today's LangGraph run with state:")
    print(initial_state)
    print("\nRunning graph...\n")

    final_state = graph.invoke(initial_state)
    print(final_state["reply"])
    print("\nNew memory written for future sessions:")
    for item in final_state.get("memories_written", []):
        print(f"- {item}")


def main() -> None:
    run_today()


if __name__ == "__main__":
    main()

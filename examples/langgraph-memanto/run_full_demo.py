#!/usr/bin/env python3
"""Run the complete cross-session LangGraph + Memanto demo."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from graph import SupportState, build_support_graph
from support_memory import DEFAULT_AGENT_ID, MemantoSupportMemory


CUSTOMER_ID = "dana-chen"


def invoke_demo_turn(
    graph,
    thread_id: str,
    message: str,
) -> SupportState:
    state: SupportState = {
        "customer_id": CUSTOMER_ID,
        "message": message,
        "recalled_memories": [],
        "response": "",
        "stored_memory_id": None,
    }
    return graph.invoke(
        state,
        config={"configurable": {"thread_id": thread_id}},
    )


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit("MOORCHEH_API_KEY not set. Copy .env.example to .env.")

    agent_id = os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID)

    with MemantoSupportMemory(api_key=api_key, agent_id=agent_id) as memory:
        graph = build_support_graph(memory)

        yesterday = invoke_demo_turn(
            graph,
            thread_id="yesterday-thread",
            message=(
                "Remember: Dana prefers concise async onboarding summaries, "
                "uses Stripe billing, and wants enterprise rollout priorities "
                "ready next week."
            ),
        )

        today = invoke_demo_turn(
            graph,
            thread_id="today-thread",
            message="What should I prioritize for Dana's onboarding today?",
        )

    print("=" * 72)
    print("Run 1: yesterday-thread stored long-term memory")
    print("=" * 72)
    print(yesterday["response"])
    print(f"Stored memory ID: {yesterday['stored_memory_id']}")

    print("\n" + "=" * 72)
    print("Run 2: today-thread starts with only a new question")
    print("=" * 72)
    print(today["message"])

    print("\nMemanto recall result:")
    for memory_item in today["recalled_memories"]:
        print(f"- {memory_item}")

    print("\nAgent response grounded in recalled memory:")
    print(today["response"])


if __name__ == "__main__":
    main()

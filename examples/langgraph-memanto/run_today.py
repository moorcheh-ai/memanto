#!/usr/bin/env python3
"""Run 2: recall yesterday's detail from a different LangGraph thread."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from graph import SupportState, build_support_graph
from support_memory import DEFAULT_AGENT_ID, MemantoSupportMemory


CUSTOMER_ID = "dana-chen"


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit("MOORCHEH_API_KEY not set. Copy .env.example to .env.")

    agent_id = os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID)

    with MemantoSupportMemory(api_key=api_key, agent_id=agent_id) as memory:
        graph = build_support_graph(memory)
        state: SupportState = {
            "customer_id": CUSTOMER_ID,
            "message": "What should I prioritize for Dana's onboarding today?",
            "recalled_memories": [],
            "response": "",
            "stored_memory_id": None,
        }
        result = graph.invoke(
            state,
            config={"configurable": {"thread_id": "today-thread"}},
        )

    print("Run 2: today-thread")
    print("Current state message:")
    print(f"- {state['message']}")
    print("\nPersistent memories recalled from Memanto:")
    for item in result["recalled_memories"]:
        print(f"- {item}")
    print("\nAgent response:")
    print(result["response"])


if __name__ == "__main__":
    main()

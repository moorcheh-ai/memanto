#!/usr/bin/env python3
"""Store customer context with the LangGraph + Memanto workflow."""

from __future__ import annotations

from dotenv import load_dotenv
from graph import build_support_memory_graph
from memory_adapter import create_memory_client


def main() -> None:
    load_dotenv()
    memory = create_memory_client()
    memory.setup()
    try:
        graph = build_support_memory_graph(memory)
        result = graph.invoke({"session": "day1"})
        print("Day 1 memories stored in Memanto")
        print(f"Agent ID: {memory.agent_id}")
        print("Stored memory IDs:")
        for memory_id in result.get("stored_memory_ids", []):
            print(f"  - {memory_id}")
    finally:
        memory.teardown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Recall stored customer context in a separate LangGraph session."""

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
        result = graph.invoke({"session": "day2"})
        print("Day 2 recalled memories from Memanto")
        print(f"Agent ID: {memory.agent_id}")
        print(f"Retrieved: {len(result.get('retrieved_memories', []))} memories")
        print()
        print(result["final_response"])
    finally:
        memory.teardown()


if __name__ == "__main__":
    main()

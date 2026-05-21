#!/usr/bin/env python3
"""Run the full LangGraph + Memanto demo in one command."""

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
        result = graph.invoke({"session": "full"})
        print("LangGraph + Memanto full demo")
        print(f"Agent ID: {memory.agent_id}")
        print(f"Stored: {len(result.get('stored_memory_ids', []))} memories")
        print(f"Retrieved: {len(result.get('retrieved_memories', []))} memories")
        print()
        print(result["final_response"])
    finally:
        memory.teardown()


if __name__ == "__main__":
    main()

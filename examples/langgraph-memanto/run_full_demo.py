"""Run the complete LangGraph + Memanto cross-session memory demo."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from memory_store import InMemoryLongTermMemory, MemantoLongTermMemory, format_memories
from support_graph import build_support_graph, seed_yesterday


def create_memory():
    load_dotenv()
    api_key = os.getenv("MOORCHEH_API_KEY")
    agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-support-memory-demo")
    offline = os.getenv("OFFLINE_DEMO", "").lower() in {"1", "true", "yes"}

    if api_key and not offline:
        memory = MemantoLongTermMemory(api_key=api_key, agent_id=agent_id)
    else:
        memory = InMemoryLongTermMemory(agent_id=agent_id)

    memory.setup()
    return memory


def run_demo() -> None:
    memory = create_memory()

    print("Day 1: storing memories outside LangGraph state")
    seed_yesterday(memory)
    print(format_memories(memory.recall("maya email receipt delayed order", limit=5)))

    print("\nDay 2: new LangGraph run with empty short-term state")
    graph = build_support_graph(memory)
    result = graph.invoke(
        {
            "user_id": "maya",
            "message": "Can you send my receipt and remind me what happened to my order?",
            "session_label": "day-two",
        }
    )

    print("\nRetrieved long-term memories:")
    print(format_memories(result["retrieved_memories"]))
    print("\nAgent response:")
    print(result["response"])
    print(f"\nStored follow-up memory: {result['stored_memory_id']}")


if __name__ == "__main__":
    run_demo()

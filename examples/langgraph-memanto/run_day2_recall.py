"""Day 2: start a new LangGraph session and recall yesterday's memories."""

from __future__ import annotations

from graph import create_support_graph
from memanto_memory import MemantoMemory


CUSTOMER_ID = "customer-aurora"


def main() -> None:
    memory = MemantoMemory.from_env()
    memory.connect()

    try:
        graph = create_support_graph(memory)
        result = graph.invoke(
            {
                "customer_id": CUSTOMER_ID,
                "user_message": "Can you help me set up the export we discussed?",
            }
        )

        print("Recalled memories:")
        for item in result.get("recalled_memories", []):
            print(item)

        print("\nAgent response:")
        print(result["response"])

        print("\nNew memories stored from Day 2:")
        for memory_id in result.get("stored_memory_ids", []):
            print(f"- {memory_id}")
    finally:
        memory.close()


if __name__ == "__main__":
    main()

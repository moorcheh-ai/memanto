from __future__ import annotations

from client_factory import build_memanto_client, deactivate_client
from memory_adapter import MemantoMemoryAdapter
from workflow import build_support_graph

AGENT_ID = "langgraph-support-memory-demo"


def main() -> None:
    client = build_memanto_client(AGENT_ID)
    adapter = MemantoMemoryAdapter(client, AGENT_ID)
    graph = build_support_graph(adapter)

    try:
        result = graph.invoke(
            {
                "customer_id": "cust-acme-42",
                "ticket_id": "ticket-1001",
                "current_ticket": "Please keep renewal updates short and actionable.",
                "new_preference": (
                    "Customer cust-acme-42 prefers concise, action-oriented "
                    "support replies with bullet points."
                ),
            }
        )

        print(result["reply"])
        print(f"\nStored preference memory: {result.get('stored_memory_id', 'n/a')}")
        print("\nRun `python run_recall_session.py` next to prove persistence.")
    finally:
        deactivate_client(client, AGENT_ID)


if __name__ == "__main__":
    main()

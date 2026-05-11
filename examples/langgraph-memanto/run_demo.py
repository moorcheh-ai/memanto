#!/usr/bin/env python3
"""
Run a minimal LangGraph customer-support example that demonstrates:

1) Storing a customer memory in Memanto.
2) Recalling it in a new local session using the same Memanto namespace.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from memanto.cli.client.sdk_client import SdkClient

from support_graph import SupportMemorySession, build_support_graph


def run_turn(graph: Any, customer_id: str, message: str) -> None:
    """Execute one graph turn and print the deterministic support reply."""
    result = graph.invoke({"customer_id": customer_id, "message": message})
    print(f"\nCustomer: {message}")
    print(f"Agent: {result['reply']}")


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit(
            "Error: MOORCHEH_API_KEY is not set. Copy .env.example to .env and fill it."
        )

    agent_id = os.environ.get("LANGGRAPH_MEMANTO_AGENT_ID", "langgraph-support-bot")
    customer_id = os.environ.get("CUSTOMER_ID", "customer-acme")

    client = SdkClient(api_key=api_key)
    try:
        try:
            client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph support demo agent namespace",
            )
            print(f"Created Memanto agent '{agent_id}'.")
        except Exception:
            print(f"Using existing Memanto agent '{agent_id}'.")

        client.activate_agent(agent_id, duration_hours=6)
        memory_session = SupportMemorySession(client=client, agent_id=agent_id)
        graph = build_support_graph(client, agent_id)

        print("\n=== Session 1: storing preference ===")
        run_turn(
            graph=graph,
            customer_id=customer_id,
            message="Customer says: remember: My preferred support channel is email.",
        )

        print("\n=== Session 2: fresh local state, same Memanto namespace ===")
        run_turn(
            graph=graph,
            customer_id=customer_id,
            message="What is my preferred support channel?",
        )

        # Optional: prove only cross-thread persistence is used by checking stored record
        memories = memory_session.recall(f"{customer_id} preferred support channel")
        print("\n=== Verification: direct Memanto recall ===")
        if memories:
            top = memories[0]
            print(f"Stored memory title: {top.get('title', 'Unknown')}")
            print(f"Stored memory content: {top.get('content', 'Unknown')}")
        else:
            print("No memories found for verification query.")

    finally:
        try:
            client.deactivate_agent(agent_id)
        except Exception:
            pass


if __name__ == "__main__":
    main()

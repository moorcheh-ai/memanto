"""Run a two-session LangGraph + Memanto support-memory demo."""

from __future__ import annotations

import argparse
import os

from memory_adapter import InMemoryMemantoStore, MemantoMemory
from support_agent import build_support_graph

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


def run_turn(memory: MemantoMemory, customer_id: str, message: str) -> dict:
    graph = build_support_graph(memory)
    return graph.invoke({"customer_id": customer_id, "message": message})


def print_turn(title: str, result: dict) -> None:
    print(f"\n== {title} ==")
    print(f"User: {result['message']}")
    print(f"Agent: {result['response']}")
    print(f"Recalled memories: {len(result.get('recalled_memories', []))}")
    print(f"Stored memories: {len(result.get('stored_memories', []))}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-id",
        default=os.getenv("MEMANTO_AGENT_ID", "langgraph-support-demo"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use local in-memory storage instead of the Memanto API.",
    )
    args = parser.parse_args()

    api_key = os.getenv("MOORCHEH_API_KEY")
    dry_run = args.dry_run or not api_key
    shared_store = InMemoryMemantoStore() if dry_run else None

    session_one_memory = MemantoMemory(
        agent_id=args.agent_id,
        api_key=api_key,
        dry_run=dry_run,
        store=shared_store,
    )
    first = run_turn(
        session_one_memory,
        customer_id="customer-42",
        message=(
            "My name is Dana. I prefer concise updates. "
            "I use the Acme workspace and need help with invoice exports."
        ),
    )
    print_turn("Session 1: capture long-term context", first)

    session_two_memory = MemantoMemory(
        agent_id=args.agent_id,
        api_key=api_key,
        dry_run=dry_run,
        store=shared_store,
    )
    second = run_turn(
        session_two_memory,
        customer_id="customer-42",
        message="Can you continue helping with my invoice export?",
    )
    print_turn("Session 2: recall context in a fresh graph run", second)

    mode = "dry-run local memory" if dry_run else "Memanto API"
    print(f"\nCompleted using {mode}.")


if __name__ == "__main__":
    main()

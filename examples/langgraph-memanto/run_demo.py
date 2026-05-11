"""Run the two-session LangGraph + Memanto demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_backends import LocalJsonMemoryBackend, MemantoSdkMemoryBackend
from support_agent import SupportAgent, run_support_turn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=["local", "memanto"],
        default="local",
        help="Use local JSON for offline review or live Memanto SDK storage.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Clear the local JSON store before running.",
    )
    parser.add_argument(
        "--agent-id",
        default="langgraph-support-demo",
        help="Memanto agent ID for the live backend.",
    )
    args = parser.parse_args()

    store_path = Path(__file__).with_name(".demo-memory.json")
    if args.backend == "local":
        backend = LocalJsonMemoryBackend(store_path)
        if args.reset_local:
            backend.reset()
    else:
        backend = MemantoSdkMemoryBackend(agent_id=args.agent_id)

    agent = SupportAgent(memory=backend)

    day_one = run_support_turn(
        agent=agent,
        thread_id="thread-day-1",
        session_label="day-1-intake",
        customer_message=(
            "I'm Priya from Northstar Dental. We prefer SMS updates. "
            "Our vendor is Kivo. Never include PHI in replies, and ask "
            "Dr. Rao for approval before escalation."
        ),
    )

    day_two = run_support_turn(
        agent=agent,
        thread_id="thread-day-2",
        session_label="day-2-fresh-thread",
        customer_message=(
            "Yesterday I gave you our clinic preferences. Can you remember "
            "them and draft a safe update about the vendor outage?"
        ),
    )

    print("=== Day 1: store memories ===")
    print(f"Thread: {day_one['thread_id']}")
    print(f"Stored: {len(day_one['persisted_memory_ids'])} memories")
    for memory in day_one["new_memories"]:
        print(f"- [{memory.memory_type}] {memory.content}")

    print("\n=== Day 2: fresh LangGraph thread recalls yesterday ===")
    print(f"Thread: {day_two['thread_id']}")
    print(f"Recalled: {len(day_two['recalled_memories'])} memories")
    for memory in day_two["recalled_memories"]:
        print(f"- [{memory.memory_type}] {memory.content}")
    print("\nAgent response:")
    print(day_two["response"])

    if len(day_two["recalled_memories"]) < 3:
        raise SystemExit("cross-session recall failed: expected at least 3 memories")
    if "Priya" not in day_two["response"] or "SMS" not in day_two["response"]:
        raise SystemExit("cross-session recall failed: response missed durable context")

    print("\nCross-session recall verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


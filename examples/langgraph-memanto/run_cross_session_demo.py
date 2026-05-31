"""Run the LangGraph + Memanto cross-session memory demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from customer_support_graph import build_customer_support_graph
from memory_backends import build_backend


SEED_MEMORIES = [
    (
        "Customer Alex is on the enterprise plan.",
        "fact",
    ),
    (
        "Customer Alex prefers email follow-ups before demos.",
        "preference",
    ),
    (
        "Invoices for Alex should stay in GBP.",
        "decision",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove cross-session recall with LangGraph and Memanto.",
    )
    parser.add_argument(
        "--backend",
        choices=["file", "memanto"],
        default="file",
        help="Use file for offline review or memanto for the real CLI backend.",
    )
    parser.add_argument(
        "--agent-id",
        default="langgraph-support-demo",
        help="Memanto agent id or source id used by the file backend.",
    )
    parser.add_argument(
        "--memory-file",
        default=".demo_memory.json",
        help="JSON file used by the offline backend.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the offline memory file before seeding.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.backend == "file" and args.reset:
        Path(args.memory_file).unlink(missing_ok=True)

    print("Session 1: yesterday's support handoff stores durable facts")
    yesterday_memory = build_backend(args)
    for content, memory_type in SEED_MEMORIES:
        yesterday_memory.remember(content, memory_type=memory_type)
        print(f"- remembered: {content}")

    print("\nSession 2: today's graph starts fresh and recalls account memory")
    today_memory = build_backend(args)
    graph = build_customer_support_graph(today_memory)
    result = graph.invoke(
        {
            "question": (
                "Alex asks whether we can book a demo tomorrow. They prefer "
                "email and ask what invoice currency we will use."
            )
        }
    )

    print("\nRecalled memories:")
    for memory in result.get("recalled_memories", []):
        print(f"- {memory}")

    print("\nGraph response:")
    print(result["response"])

    if result.get("stored_learning"):
        print("\nStored new learning:")
        print(result["stored_learning"])


if __name__ == "__main__":
    main()

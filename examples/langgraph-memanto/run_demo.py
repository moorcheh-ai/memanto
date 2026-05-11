#!/usr/bin/env python3
"""Run the LangGraph + Memanto memory demo.

Examples:
    python run_demo.py --mock
    python run_demo.py --phase learn
    python run_demo.py --phase recall
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable

from dotenv import load_dotenv
from graph import build_memory_graph
from memory_store import InMemoryMemoryStore, MemantoMemoryStore, MemoryStore

DEFAULT_AGENT_ID = "langgraph-memanto-demo"
DEFAULT_USER_ID = "demo-user"
DEFAULT_RECALL_QUERY = "What do you remember about my preferences and project?"
LEARNING_MESSAGES = [
    (
        "Hi, my name is Sam Rivera. I prefer concise bullet points. "
        "My project is a LangGraph customer support bot."
    ),
    "Remember that follow-up answers should include runnable Python examples.",
    "I am allergic to peanuts and I like practical architecture diagrams.",
]


def main() -> None:
    load_dotenv()
    args = parse_args()

    store = build_store(args)
    try:
        if args.phase in {"learn", "both"}:
            run_learning_phase(store, LEARNING_MESSAGES)

        if args.phase == "both" and not args.mock:
            print("\nReopening Memanto session and rebuilding the graph...")
            store.close()
            time.sleep(args.index_wait)
            store = build_store(args)

        if args.phase in {"recall", "both"}:
            run_recall_phase(store, args.query)
    finally:
        store.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangGraph + Memanto demo")
    parser.add_argument(
        "--phase",
        choices=("learn", "recall", "both"),
        default="both",
        help="Run only the memory-write phase, only recall, or both.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID),
        help="Memanto agent ID/namespace used for persistence.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_RECALL_QUERY,
        help="Question used during the recall phase.",
    )
    parser.add_argument(
        "--index-wait",
        type=float,
        default=2.0,
        help="Seconds to wait before recall so remote indexing can settle.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use an in-memory adapter for tests/demos without a Moorcheh API key.",
    )
    return parser.parse_args()


def build_store(args: argparse.Namespace) -> MemoryStore:
    if args.mock:
        return InMemoryMemoryStore()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "MOORCHEH_API_KEY is required for the real Memanto demo. "
            "Copy .env.example to .env, add your key, or rerun with --mock.",
            file=sys.stderr,
        )
        sys.exit(1)

    return MemantoMemoryStore(
        api_key=api_key,
        agent_id=args.agent_id,
        description="LangGraph example that persists user memory in Memanto",
    )


def run_learning_phase(store: MemoryStore, messages: Iterable[str]) -> None:
    print("\n=== Phase 1: learn and persist memories ===")
    graph = build_memory_graph(store)

    for index, message in enumerate(messages, start=1):
        print(f"\nUser message {index}: {message}")
        result = graph.invoke({"user_id": DEFAULT_USER_ID, "message": message})
        print(result["response"])


def run_recall_phase(store: MemoryStore, query: str) -> None:
    print("\n=== Phase 2: recall in a fresh LangGraph run ===")
    print(f"User question: {query}")

    # Build a fresh graph object. No LangGraph checkpointer is used; any answer
    # must come from the MemoryStore, which is Memanto in real mode.
    graph = build_memory_graph(store)
    result = graph.invoke({"user_id": DEFAULT_USER_ID, "message": query})
    print(result["response"])


if __name__ == "__main__":
    main()

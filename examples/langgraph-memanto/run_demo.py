#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from graph import build_support_graph
from memory_store import LocalJsonMemoryStore, MemantoMemoryStore

AGENT_ID = "langgraph-support-memory"
LOCAL_PATH = Path(__file__).with_name(".memanto-langgraph-local.json")


def main() -> None:
    load_dotenv()
    args = parse_args()
    store = build_store(args)

    try:
        if args.reset_local and isinstance(store, LocalJsonMemoryStore):
            store.clear()

        if args.mode in {"learn", "full"}:
            run_learn(store)
        if args.mode in {"recall", "full"}:
            if args.mode == "full" and args.backend == "local":
                store = LocalJsonMemoryStore(args.local_path)
            run_recall(store)
    finally:
        close = getattr(store, "close", None)
        if close:
            close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument("--mode", choices=["learn", "recall", "full"], default="full")
    parser.add_argument("--reset-local", action="store_true")
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", AGENT_ID),
    )
    parser.add_argument(
        "--local-path",
        type=Path,
        default=Path(os.environ.get("MEMANTO_LANGGRAPH_LOCAL_PATH", str(LOCAL_PATH))),
    )
    return parser.parse_args()


def build_store(args: argparse.Namespace):
    if args.backend == "local":
        return LocalJsonMemoryStore(args.local_path)

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit("MOORCHEH_API_KEY is required for --backend memanto")
    return MemantoMemoryStore(api_key=api_key, agent_id=args.agent_id)


def run_learn(store: Any) -> None:
    graph = build_support_graph(store)
    result = graph.invoke(
        {
            "customer_id": "Maya",
            "thread_id": "session-one",
            "message": (
                "I am Maya. My order is AR-8841, and I prefer replacement "
                "units before refunds."
            ),
        }
    )
    print_result("Session one stored durable memory", result)


def run_recall(store: Any) -> None:
    graph = build_support_graph(store)
    result = graph.invoke(
        {
            "customer_id": "Maya",
            "thread_id": "session-two",
            "message": "What should you remember about my last order?",
        }
    )
    print_result("Session two recalled from durable memory", result)


def print_result(label: str, result: dict[str, Any]) -> None:
    print(f"\n{label}")
    print("=" * len(label))
    print(f"thread_id: {result['thread_id']}")
    print(f"answer: {result['answer']}")
    if result.get("stored_memory_titles"):
        print("stored:")
        for title in result["stored_memory_titles"]:
            print(f"- {title}")
    if result.get("recalled_memories"):
        print("recalled:")
        for memory in result["recalled_memories"]:
            print(f"- {memory['title']}: {memory['content']}")


if __name__ == "__main__":
    main()

"""Run a two-session LangGraph + Memanto memory demo.

Run this file twice or run `--mode full`.  Session A stores a durable memory;
Session B starts as a fresh LangGraph invocation and recalls it from Memanto.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from graph import build_research_graph
from memory_store import OfflineJsonMemoryStore, build_memory_store


def run_turn(message: str, session: str, *, preview: bool = False) -> dict[str, object]:
    store = (
        OfflineJsonMemoryStore(Path(__file__).with_name(".memanto-langgraph-demo.json"))
        if preview
        else build_memory_store()
    )
    graph = build_research_graph(store)
    return graph.invoke({"session": session, "user_message": message})


def run_full(preview: bool = False, reset: bool = False) -> None:
    memory_file = Path(__file__).with_name(".memanto-langgraph-demo.json")
    if reset and memory_file.exists():
        memory_file.unlink()

    print("SESSION A — store durable research context")
    first = run_turn(
        "Remember Ava is researching privacy-preserving AI assistants and prefers concise implementation checklists.",
        "session-a",
        preview=preview,
    )
    print(first["response"])
    print(f"Stored memory id: {first.get('stored_memory_id', 'live-store')}\n")

    print("SESSION B — new graph run, recall durable context")
    second = run_turn(
        "What do you remember about Ava's research preferences?",
        "session-b",
        preview=preview,
    )
    print(second["response"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["session-a", "session-b", "full"], default="full")
    parser.add_argument("--preview", action="store_true", help="Use local JSON memory instead of live Memanto credentials")
    parser.add_argument("--reset", action="store_true", help="Clear local preview memory before running")
    args = parser.parse_args()

    if args.mode == "full":
        run_full(preview=args.preview, reset=args.reset)
    elif args.mode == "session-a":
        result = run_turn(
            "Remember Ava is researching privacy-preserving AI assistants and prefers concise implementation checklists.",
            "session-a",
            preview=args.preview,
        )
        print(result["response"])
        print(f"Stored memory id: {result.get('stored_memory_id', 'live-store')}")
    else:
        result = run_turn(
            "What do you remember about Ava's research preferences?",
            "session-b",
            preview=args.preview,
        )
        print(result["response"])


if __name__ == "__main__":
    main()

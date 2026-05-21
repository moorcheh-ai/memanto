from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from memory_store import build_memory_store
from support_graph import run_support_turn


def run_isolated_session(user_id: str, message: str, offline: bool):
    memory_store = build_memory_store(offline=offline)
    memory_store.setup()
    try:
        return run_support_turn(memory_store, user_id=user_id, message=message)
    finally:
        memory_store.close()


def print_turn(title: str, result) -> None:
    print(f"\n{'=' * 72}")
    print(title)
    print(f"{'=' * 72}")
    print("User:", result["user_id"])
    print("Message:", result["message"])
    print("Recalled memories:")
    for memory in result.get("recalled_memories", []):
        print(f"  - {memory}")
    if not result.get("recalled_memories"):
        print("  - none")
    print("Stored preferences:")
    for preference in result.get("extracted_preferences", []):
        print(f"  - {preference}")
    if not result.get("extracted_preferences"):
        print("  - none")
    print("Response:", result["response"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prove cross-session recall with LangGraph + Memanto."
    )
    parser.add_argument("--user", default="alex", help="Stable user identifier")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local JSON storage instead of Memanto for smoke testing",
    )
    parser.add_argument(
        "--reset-offline-store",
        action="store_true",
        help="Delete the local JSON store before an offline demo run",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.offline and args.reset_offline_store:
        Path(".langgraph_memanto_demo.json").unlink(missing_ok=True)

    first = run_isolated_session(
        user_id=args.user,
        message="I prefer concise answers and dark mode.",
        offline=args.offline,
    )
    second = run_isolated_session(
        user_id=args.user,
        message="What dashboard style should you use for me?",
        offline=args.offline,
    )

    print_turn("Session 1: store a preference", first)
    print_turn("Session 2: fresh graph state recalls Memanto memory", second)


if __name__ == "__main__":
    main()


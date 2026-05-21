from __future__ import annotations

import argparse

from dotenv import load_dotenv

from memory_store import build_memory_store
from support_graph import run_support_turn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one LangGraph + Memanto turn.")
    parser.add_argument("--user", default="alex", help="Stable user identifier")
    parser.add_argument("--message", required=True, help="User message for this turn")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local JSON storage instead of Memanto for smoke testing",
    )
    args = parser.parse_args()

    load_dotenv()
    memory_store = build_memory_store(offline=args.offline)
    try:
        memory_store.setup()
        result = run_support_turn(memory_store, user_id=args.user, message=args.message)
    finally:
        memory_store.close()

    print("\nUser:", result["user_id"])
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


if __name__ == "__main__":
    main()

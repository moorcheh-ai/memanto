"""Day 2 demo: recall day-1 customer memories in a fresh graph run."""

from __future__ import annotations

from memory_store import create_memory_store
from support_agent import format_memories, run_support_turn


CUSTOMER_ID = "acme-ops"
MESSAGE = (
    "Before I reply to ACME Ops, what dashboard style and follow-up timing "
    "should I remember?"
)


def main() -> None:
    store = create_memory_store()
    try:
        state = run_support_turn(store, CUSTOMER_ID, MESSAGE)
        print("Day 2 recalled memories:")
        print(format_memories(state["recalled_memories"]))

        print("\nAgent response:")
        print(state["response"])
    finally:
        store.close()


if __name__ == "__main__":
    main()

"""Day 1 demo: store customer facts in Memanto through LangGraph."""

from __future__ import annotations

from memory_store import create_memory_store, reset_local_store
from support_agent import format_memories, run_support_turn


CUSTOMER_ID = "acme-ops"
MESSAGE = (
    "ACME Ops is on the Enterprise plan. Their admin works in Europe/London, "
    "prefers a dark analytics dashboard, and asked for a Tuesday follow-up "
    "about CSV export limits."
)


def main() -> None:
    reset_local_store()
    store = create_memory_store()
    try:
        state = run_support_turn(store, CUSTOMER_ID, MESSAGE)
        print("Day 1 saved memory ids:")
        for memory_id in state["saved_memory_ids"]:
            print(f"- {memory_id}")

        print("\nDay 1 recalled before saving:")
        print(format_memories(state["recalled_memories"]))
    finally:
        store.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from graph import build_graph, default_agent_id
from memory_store import LocalJsonMemoryStore, build_memory_store

YESTERDAY_MESSAGE = (
    "I am Riley. Please remember that I use the Northstar dashboard theme, "
    "invoices should arrive every Friday with the purchase order in the "
    "subject, our migration launches on May 28, and support escalations "
    "should go to Ada in support ops."
)
TODAY_MESSAGE = (
    "Fresh thread: what should you remember about Riley's dashboard, invoices, "
    "migration, and support escalations?"
)


def run_demo(backend: str = "local", reset_local: bool = False) -> dict[str, object]:
    store = build_memory_store(backend)
    if reset_local and isinstance(store, LocalJsonMemoryStore):
        store.reset()

    graph = build_graph(store)
    agent_id = default_agent_id()

    yesterday = graph.invoke(
        {
            "agent_id": agent_id,
            "session_id": "support-yesterday",
            "user_message": YESTERDAY_MESSAGE,
        }
    )
    today = graph.invoke(
        {
            "agent_id": agent_id,
            "session_id": "support-today",
            "user_message": TODAY_MESSAGE,
        }
    )

    return {"yesterday": yesterday, "today": today}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument("--reset-local", action="store_true")
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Reserved for local smoke scripts; defaults to /tmp.",
    )
    args = parser.parse_args()

    result = run_demo(args.backend, args.reset_local)
    yesterday = result["yesterday"]
    today = result["today"]

    print("Session 1 stored memory ids:")
    for memory_id in yesterday.get("stored_memory_ids", []):
        print(f"- {memory_id}")

    print("\nSession 2 recalled memories:")
    for memory in today.get("recalled_memories", []):
        print(f"- {memory['title']}: {memory['content']}")

    print("\nAgent response:")
    print(today["response"])


if __name__ == "__main__":
    main()

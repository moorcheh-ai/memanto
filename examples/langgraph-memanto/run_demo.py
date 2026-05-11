"""Run the LangGraph + Memanto cross-session memory demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from langgraph_memanto import (
    JsonMemoryStore,
    MemantoMemoryStore,
    build_graph,
    run_turn,
)


SESSION_ONE = (
    "I'm Maya from Nova Clinics. Please always escalate CSV export bugs "
    "to Priya. I prefer terse bullet replies. The launch review is "
    "Tuesday at 9 AM Bangkok time."
)

SESSION_TWO = (
    "A new ticket says CSV exports are failing before launch. "
    "What context should the support agent use?"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstrate Memanto durable memory across LangGraph sessions.",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "memanto"],
        default="local",
        help="Use local JSON memory or the real Memanto SDK.",
    )
    parser.add_argument(
        "--store-path",
        default=".langgraph-memanto-demo.jsonl",
        help="Local JSON store path for --backend local.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Delete the local JSON store before running.",
    )
    args = parser.parse_args()

    load_dotenv()

    if args.backend == "local":
        memory = JsonMemoryStore(Path(args.store_path))
        if args.reset_local:
            memory.reset()
    else:
        memory = MemantoMemoryStore.from_env()

    graph = build_graph(memory)

    first = run_turn(
        graph=graph,
        session_id="session-1-intake",
        user_message=SESSION_ONE,
    )
    second = run_turn(
        graph=graph,
        session_id="session-2-handoff",
        user_message=SESSION_TWO,
    )

    print("SESSION 1: intake")
    print(first["answer"])
    print()
    print("SESSION 2: new LangGraph thread")
    print(second["answer"])
    print()
    print(f"Session 2 recalled {len(second['recalled_memories'])} memories.")


if __name__ == "__main__":
    main()

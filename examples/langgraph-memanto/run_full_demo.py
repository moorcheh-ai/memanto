#!/usr/bin/env python3
"""Run the complete two-session LangGraph + Memanto demo."""

from __future__ import annotations

from graph import (
    CUSTOMER_ID,
    DAY_1_MESSAGE,
    DAY_2_MESSAGE,
    build_support_graph,
    print_run_summary,
)
from memory_adapter import create_memory_backend


def run_session(label: str, message: str, store: bool = True) -> None:
    memory = create_memory_backend()
    memory.setup()
    try:
        graph = build_support_graph(memory)
        initial_state = {
            "customer_id": CUSTOMER_ID,
            "message": message,
        }
        if not store:
            initial_state["memories_to_store"] = []
            initial_state["stored_memory_ids"] = []
        result = graph.invoke(initial_state)
        print_run_summary(label, result)
    finally:
        memory.close()


def main() -> None:
    run_session("Day 1: store durable customer context", DAY_1_MESSAGE)
    run_session(
        "Day 2: new LangGraph run recalls yesterday's context",
        DAY_2_MESSAGE,
        store=False,
    )


if __name__ == "__main__":
    main()

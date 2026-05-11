#!/usr/bin/env python3
"""
Session 2: start with empty LangGraph state and recall yesterday's context.

Run this after `run_day1_store.py` to show that the graph can personalize the
reply from Memanto, even though no previous messages are passed in state.
"""

from __future__ import annotations

from graph import CUSTOMER_ID, DAY_2_MESSAGE, build_support_graph, print_run_summary
from memory_adapter import create_memory_backend


def main() -> None:
    memory = create_memory_backend()
    memory.setup()
    try:
        graph = build_support_graph(memory)
        result = graph.invoke(
            {
                "customer_id": CUSTOMER_ID,
                "message": DAY_2_MESSAGE,
                "memories_to_store": [],
                "stored_memory_ids": [],
            }
        )
        print_run_summary("Day 2: recalled context from a fresh graph run", result)
    finally:
        memory.close()


if __name__ == "__main__":
    main()

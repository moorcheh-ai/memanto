#!/usr/bin/env python3
"""Session 1: store customer details in Memanto through a LangGraph run."""

from __future__ import annotations

from graph import CUSTOMER_ID, DAY_1_MESSAGE, build_support_graph, print_run_summary
from memory_adapter import create_memory_backend


def main() -> None:
    memory = create_memory_backend()
    memory.setup()
    try:
        graph = build_support_graph(memory)
        result = graph.invoke(
            {
                "customer_id": CUSTOMER_ID,
                "message": DAY_1_MESSAGE,
            }
        )
        print_run_summary("Day 1: stored customer context", result)
    finally:
        memory.close()


if __name__ == "__main__":
    main()

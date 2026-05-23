#!/usr/bin/env python3
"""
Run 2: build a LangGraph answer from memories stored in a prior session.
"""

from __future__ import annotations

from dotenv import load_dotenv

from graph import build_support_graph
from memory_tools import MemantoMemory


def main() -> None:
    load_dotenv()

    memory = MemantoMemory.from_env()
    memory.ensure_agent()

    graph = build_support_graph(memory)
    result = graph.invoke(
        {
            "customer_id": "ACME",
            "message": "Can you help me configure deployment alerts?",
            "recalled_memory": "",
            "response": "",
        }
    )

    print(result["response"])


if __name__ == "__main__":
    main()

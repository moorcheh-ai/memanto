#!/usr/bin/env python3
"""
Run 2 ("today"): recall the fact stored by run_ingest.py.

This script builds a *fresh* LangGraph (no checkpointer, no shared
state with run_ingest.py) and asks a question that can only be
answered by reading the memory written in the previous run. Because
the graph holds zero prior thread state, a correct answer proves
that the memory lives in Memanto, not in LangGraph.

Usage:
    python run_recall.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from graph import build_graph
from memanto_tools import MemantoSetup

DEFAULT_AGENT_ID = "langgraph-support-bot"


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)

    agent_id = os.environ.get("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID)

    setup = MemantoSetup(api_key)
    client = setup.setup(
        agent_id=agent_id,
        description="Long-term memory for the LangGraph support bot example",
    )

    print(f"\n{'=' * 60}")
    print("  LangGraph + Memanto - Recall run ('today')")
    print(f"  Agent ID: {agent_id}")
    print(f"{'=' * 60}")
    print("  (Fresh graph, no checkpoint — answers must come from Memanto)")
    print()

    try:
        graph = build_graph(client, agent_id)
        result = graph.invoke(
            {
                "user_input": (
                    "Who runs the support desk and what's the response SLA?"
                ),
                "mode": "recall",
            }
        )

        print(result.get("response", ""))
    finally:
        setup.teardown(agent_id)


if __name__ == "__main__":
    main()

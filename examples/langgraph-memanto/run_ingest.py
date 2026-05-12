#!/usr/bin/env python3
"""
Run 1 ("yesterday"): ingest a user fact into Memanto via LangGraph.

This script kicks off a LangGraph run whose `remember` node calls
Memanto's `remember` tool. The fact is stored in Memanto's namespace
for `agent_id`, NOT in any LangGraph checkpoint.

Run `python run_recall.py` afterwards (in a brand-new process — a
different "session") to see the graph pull the fact back from
Memanto with zero LangGraph thread state carried over.

Usage:
    python run_ingest.py
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
    print("  LangGraph + Memanto - Ingest run ('yesterday')")
    print(f"  Agent ID: {agent_id}")
    print(f"{'=' * 60}\n")

    try:
        graph = build_graph(client, agent_id)
        result = graph.invoke(
            {
                "user_input": (
                    "Hi, my name is Dana and I run the Memanto support desk. "
                    "Our preferred response language is English and our SLA is 4 hours."
                ),
                "mode": "ingest",
                "fact_type": "fact",
                "fact_title": "Support contact: Dana (Memanto support desk)",
                "fact_content": (
                    "User Dana runs the Memanto support desk. Preferred language: "
                    "English. Response SLA: 4 hours."
                ),
                "fact_tags": "user,support,sla",
            }
        )

        print(result.get("response", ""))
        print(
            "\nFact written to Memanto. Now run `python run_recall.py` in a fresh "
            "process to prove cross-session recall without a LangGraph checkpoint."
        )
    finally:
        setup.teardown(agent_id)


if __name__ == "__main__":
    main()

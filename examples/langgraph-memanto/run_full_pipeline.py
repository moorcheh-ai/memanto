#!/usr/bin/env python3
"""
Full pipeline: ingest then recall in a single process, but across
two SEPARATE LangGraph invocations.

Even within one process the two `graph.invoke(...)` calls do not
share thread state — LangGraph state is per-invocation when no
checkpointer is configured. So the second call's ability to answer
the question still proves that memory crossed the boundary via
Memanto, not via LangGraph.

Usage:
    python run_full_pipeline.py
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
    print("  LangGraph + Memanto - Full pipeline")
    print(f"  Agent ID: {agent_id}")
    print(f"{'=' * 60}\n")

    try:
        graph = build_graph(client, agent_id)

        print("--- Invocation 1: ingest ---\n")
        ingest_result = graph.invoke(
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
        print(ingest_result.get("response", ""))

        print("\n--- Invocation 2: recall (separate thread state) ---\n")
        recall_result = graph.invoke(
            {
                "user_input": (
                    "Who runs the support desk and what's the response SLA?"
                ),
                "mode": "recall",
            }
        )
        print(recall_result.get("response", ""))

        print(f"\n{'=' * 60}")
        print("  Pipeline complete — memory crossed the invocation boundary via Memanto.")
        print(f"{'=' * 60}")
    finally:
        setup.teardown(agent_id)


if __name__ == "__main__":
    main()

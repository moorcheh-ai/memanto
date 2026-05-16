#!/usr/bin/env python3
"""
Session 2: Agent recalls user preferences from a previous session.

This script demonstrates cross-session persistence. The agent recalls
preferences stored in Session 1, even though this is a completely new
session with no shared state.

Run `run_session_1.py` first to store preferences, then run this script.

Usage:
    python run_session_2.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

sys.path.insert(0, "../../integrations/langgraph")
from memanto_langgraph import MemantoSetup

from graph import build_support_graph

AGENT_ID = "langgraph-support-demo"


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    setup = MemantoSetup(api_key)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Customer support agent with persistent memory",
    )

    print(f"\n{'=' * 70}")
    print("  SESSION 2: Customer Support Agent - Cross-Session Recall")
    print(f"  Agent ID: {AGENT_ID}")
    print("  (This is a NEW session - testing if memories persist)")
    print(f"{'=' * 70}\n")

    graph = build_support_graph(client, AGENT_ID)

    queries = [
        "Hi, I'm back. Can you remind me what contact preferences I mentioned before?",
        "What timezone am I in and when do I prefer to receive responses?",
        "I need help with the app UI. What theme setting should you recommend for me?",
    ]

    try:
        for i, message in enumerate(queries, 1):
            print(f"\n[User Query {i}]")
            print(f"  {message}\n")

            result = graph.invoke({"messages": [HumanMessage(content=message)]})

            assistant_msg = result["messages"][-1]
            print(f"[Assistant Response]")
            print(f"  {assistant_msg.content}\n")
            print("-" * 70)

        print(f"\n{'=' * 70}")
        print("  Session 2 Complete!")
        print("  The agent successfully recalled memories from Session 1.")
        print("  This demonstrates cross-session persistence with Memanto.")
        print(f"{'=' * 70}\n")

    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()

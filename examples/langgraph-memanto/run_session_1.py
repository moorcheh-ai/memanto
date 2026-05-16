#!/usr/bin/env python3
"""
Session 1: Customer shares preferences with the support agent.

This script demonstrates the first session where a user interacts with
the support agent and shares their preferences. The agent stores these
in Memanto for cross-session persistence.

Run this first, then run `run_session_2.py` to see the agent recall
the stored preferences in a completely new session.

Usage:
    python run_session_1.py
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
    print("  SESSION 1: Customer Support Agent - Initial Interaction")
    print(f"  Agent ID: {AGENT_ID}")
    print(f"{'=' * 70}\n")

    graph = build_support_graph(client, AGENT_ID)

    conversations = [
        "Hi! I'm Alex. I prefer to be contacted via email rather than phone calls.",
        "Also, I'm in the Pacific timezone and prefer responses in the morning.",
        "One more thing - I use dark mode for all my apps. Please note that for any UI suggestions.",
    ]

    try:
        for i, message in enumerate(conversations, 1):
            print(f"\n[User Message {i}]")
            print(f"  {message}\n")

            result = graph.invoke({"messages": [HumanMessage(content=message)]})

            assistant_msg = result["messages"][-1]
            print(f"[Assistant Response]")
            print(f"  {assistant_msg.content}\n")
            print("-" * 70)

        print(f"\n{'=' * 70}")
        print("  Session 1 Complete!")
        print("  Preferences have been stored in Memanto.")
        print("  Run `python run_session_2.py` to test cross-session recall.")
        print(f"{'=' * 70}\n")

    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()

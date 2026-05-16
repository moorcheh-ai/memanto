#!/usr/bin/env python3
"""
Full Demo: Both sessions in a single run.

This script runs both Session 1 and Session 2 sequentially to demonstrate
the complete cross-session memory flow. It creates a new session for each
phase to simulate real-world usage.

Usage:
    python run_full_demo.py
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

sys.path.insert(0, "../../integrations/langgraph")
from memanto_langgraph import MemantoSetup

from graph import build_support_graph

AGENT_ID = "langgraph-support-demo"


def run_session_1(setup: MemantoSetup) -> None:
    """First session: User shares preferences."""
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Customer support agent with persistent memory",
    )

    print(f"\n{'=' * 70}")
    print("  PHASE 1: User Shares Preferences")
    print(f"{'=' * 70}\n")

    graph = build_support_graph(client, AGENT_ID)

    conversations = [
        "Hi! I'm Alex. I prefer to be contacted via email rather than phone calls.",
        "I'm in the Pacific timezone and prefer responses in the morning.",
        "I use dark mode for all my apps. Please remember that.",
    ]

    for message in conversations:
        print(f"[User] {message}")
        result = graph.invoke({"messages": [HumanMessage(content=message)]})
        print(f"[Agent] {result['messages'][-1].content}\n")

    setup.teardown(AGENT_ID)
    print("[Session ended]\n")


def run_session_2(setup: MemantoSetup) -> None:
    """Second session: Agent recalls preferences from previous session."""
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Customer support agent with persistent memory",
    )

    print(f"\n{'=' * 70}")
    print("  PHASE 2: Testing Cross-Session Recall")
    print("  (New session - memories should persist from Phase 1)")
    print(f"{'=' * 70}\n")

    graph = build_support_graph(client, AGENT_ID)

    queries = [
        "What are my contact preferences?",
        "What timezone am I in?",
        "What UI theme should you recommend for me?",
    ]

    for query in queries:
        print(f"[User] {query}")
        result = graph.invoke({"messages": [HumanMessage(content=query)]})
        print(f"[Agent] {result['messages'][-1].content}\n")

    setup.teardown(AGENT_ID)
    print("[Session ended]\n")


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY not set.")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set.")
        sys.exit(1)

    print(f"\n{'#' * 70}")
    print("  MEMANTO + LANGGRAPH: Cross-Session Memory Demo")
    print(f"  Agent ID: {AGENT_ID}")
    print(f"{'#' * 70}")

    setup = MemantoSetup(api_key)

    try:
        run_session_1(setup)

        print("\n[Simulating session gap - waiting 2 seconds...]\n")
        time.sleep(2)

        run_session_2(setup)

        print(f"{'#' * 70}")
        print("  Demo Complete!")
        print("  The agent successfully demonstrated cross-session memory.")
        print(f"{'#' * 70}\n")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

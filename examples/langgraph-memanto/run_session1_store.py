#!/usr/bin/env python3
"""
Session 1: Customer Support Agent stores customer context in Memanto.

This script demonstrates a LangGraph agent that classifies a query
as "remember" intent and stores new information in persistent memory.
Run this first, then run session2_recall.py in a separate process
to prove cross-session memory persistence.

Usage:
    python run_session1_store.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langgraph_memanto import create_memanto_agent


def main():
    print("
" + "=" * 60)
    print("  Session 1: Storing Customer Context in Memanto")
    print("=" * 60 + "
")

    # Create the agent
    print("Initializing LangGraph + Memanto agent...")
    agent = create_memanto_agent(
        agent_id="support-agent-demo",
        pattern="support",
    )
    print("Agent ready!
")

    # Simulate a support agent receiving customer info
    queries = [
        "Customer Alice Johnson prefers email communication over phone calls. She has been a premium member since 2024.",
        "Alice reported a billing discrepancy on her March invoice - was charged twice for the same subscription period.",
        "We decided to issue Alice a full refund for the duplicate charge and extend her subscription by one month as compensation.",
    ]

    for i, query in enumerate(queries, 1):
        print(f"
--- Query {i} ---")
        print(f"Input: {query}
")

        result = agent.invoke({
            "query": query,
            "session_id": "session-1",
        })

        classification = result.get("classification", "unknown")
        tool_result = result.get("tool_result", "")
        final_response = result.get("final_response", "")

        print(f"Classification: {classification}")
        print(f"Tool result: {tool_result[:200]}...")
        print(f"Response: {final_response[:200]}...")

    print("
" + "=" * 60)
    print("  Session 1 complete! Memories stored in Memanto.")
    print("  Now run session2_recall.py to prove cross-session persistence.")
    print("=" * 60 + "
")


if __name__ == "__main__":
    main()

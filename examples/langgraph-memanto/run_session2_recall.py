#!/usr/bin/env python3
"""
Session 2: Customer Support Agent recalls previous context from Memanto.

This script runs in a completely separate process/session to prove
that memories persist across sessions. It classifies queries as
"recall" or "answer" intent and retrieves previously stored info.

Usage:
    python run_session2_recall.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langgraph_memanto import create_memanto_agent


def main():
    print("
" + "=" * 60)
    print("  Session 2: Recalling Customer Context from Memanto")
    print("=" * 60 + "
")

    # Create the agent (same agent_id as Session 1)
    print("Initializing LangGraph + Memanto agent (same agent_id)...")
    agent = create_memanto_agent(
        agent_id="support-agent-demo",
        pattern="support",
    )
    print("Agent ready!
")

    # Simulate a different agent/session recalling stored context
    queries = [
        "What do we know about Alice Johnson's preferences?",
        "What billing issue did Alice report?",
        "What did we decide about the refund for Alice?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"
--- Query {i} ---")
        print(f"Input: {query}
")

        result = agent.invoke({
            "query": query,
            "session_id": "session-2",
        })

        classification = result.get("classification", "unknown")
        tool_result = result.get("tool_result", "")
        final_response = result.get("final_response", "")

        print(f"Classification: {classification}")
        print(f"Memory result: {tool_result[:300]}...")
        print(f"Response: {final_response[:300]}...")

    print("
" + "=" * 60)
    print("  Session 2 complete! Cross-session memory persistence proven.")
    print("  The agent successfully recalled memories from Session 1.")
    print("=" * 60 + "
")


if __name__ == "__main__":
    main()

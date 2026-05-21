#!/usr/bin/env python3
"""
Session 1: Store Customer Context

Demonstrates the "remember" side of the Memanto + LangGraph integration.
This script simulates a customer support interaction where the agent
learns about a customer's preferences and stores them in Memanto.

Run this first, then run run_session2_recall.py to prove persistence.

Usage:
    python run_session1_store.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CUSTOMER_ID = "customer-acme-001"
CUSTOMER_DESC = "ACME Corp support agent with long-term memory"

# Conversation turns that reveal customer preferences and issues
CONVERSATION_TURNS = [
    "Hi, I'm Jane from ACME Corp. We've been using your Enterprise plan for about 6 months now.",
    "We mainly use the API for automated report generation. Our team prefers CSV format over JSON because it's easier for the finance team to work with.",
    "We had an issue last month with rate limiting during peak hours (9-11 AM EST). It was resolved by increasing our quota, but I want to make sure it doesn't happen again.",
    "Also, we're planning to migrate to v2 of the API next quarter. Could you send us the migration guide?",
    "One more thing — our account manager is Bob Williams. He's been great. We'd like to keep him as our primary contact.",
]


def main() -> None:
    """Run Session 1: Store customer context in Memanto."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("ERROR: Set MOORCHEH_API_KEY in .env or environment")
        sys.exit(1)
    if not openai_key:
        print("ERROR: Set OPENAI_API_KEY in .env or environment")
        sys.exit(1)

    # Import here to avoid import errors before env is loaded
    from memanto_tools import MemantoToolkit
    from agent import build_support_agent_graph, run_conversation
    from langchain_core.messages import HumanMessage

    print("=" * 60)
    print("  SESSION 1: Storing Customer Context in Memanto")
    print("=" * 60)
    print()

    # Initialize Memanto toolkit
    toolkit = MemantoToolkit(api_key=api_key)
    toolkit.setup(
        agent_id=CUSTOMER_ID,
        pattern="support",
        description=CUSTOMER_DESC,
        duration_hours=6,
    )
    print(f"[OK] Memanto agent '{CUSTOMER_ID}' activated")
    print()

    # Build the LangGraph agent
    graph = build_support_agent_graph(
        toolkit=toolkit,
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key=openai_key,
        openai_base_url=os.environ.get("OPENAI_BASE_URL"),
    )
    print("[OK] LangGraph agent built")
    print()

    # Run conversation turns
    messages = []
    for i, turn in enumerate(CONVERSATION_TURNS, 1):
        print(f"--- Turn {i}/{len(CONVERSATION_TURNS)} ---")
        print(f"Customer: {turn}")
        print()

        messages = run_conversation(
            graph=graph,
            customer_id=CUSTOMER_ID,
            user_message=turn,
            existing_messages=messages,
        )

        # Print the agent's reply (last AIMessage)
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"Agent: {msg.content[:200]}")
                break
        print()

    # Verify memories were stored
    print("=" * 60)
    print("  Verifying stored memories...")
    print("=" * 60)
    result = toolkit.recall(query="ACME Corp preferences and issues", limit=10)
    memories = result.get("memories", [])
    print(f"\nFound {len(memories)} memories:")
    for mem in memories:
        print(f"  - [{mem.get('type')}] {mem.get('title')} "
              f"(confidence: {mem.get('confidence')})")
    print()

    # Teardown
    toolkit.teardown()
    print("[OK] Session ended. Memories persist in Memanto.")
    print()
    print("Next: Run 'python run_session2_recall.py' to prove cross-session persistence!")


if __name__ == "__main__":
    main()

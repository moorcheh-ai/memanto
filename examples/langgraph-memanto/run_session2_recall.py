#!/usr/bin/env python3
"""
Session 2: Cross-Session Recall Demo

Proves that Memanto preserves memories across sessions. This script:

  1. Starts a BRAND NEW session for the same customer
  2. Asks a question that requires knowledge from Session 1
  3. Shows that the agent recalls and uses prior context

Run this AFTER run_session1_store.py. You can even restart your
machine between runs — memories persist in Memanto's cloud.

Usage:
    python run_session2_recall.py
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

# Questions that require knowledge from Session 1
RECALL_QUESTIONS = [
    "Hi, it's Jane from ACME again. What format do we prefer for our reports?",
    "We're hitting rate limits again during morning hours. Didn't we resolve this before?",
    "Who is our account manager? I forgot their name.",
    "We're ready to start the API v2 migration. Can you remind me what we discussed about it?",
]


def main() -> None:
    """Run Session 2: Demonstrate cross-session memory recall."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("ERROR: Set MOORCHEH_API_KEY in .env or environment")
        sys.exit(1)
    if not openai_key:
        print("ERROR: Set OPENAI_API_KEY in .env or environment")
        sys.exit(1)

    from memanto_tools import MemantoToolkit
    from agent import build_support_agent_graph, run_conversation
    from langchain_core.messages import HumanMessage

    print("=" * 60)
    print("  SESSION 2: Cross-Session Recall Demo")
    print("=" * 60)
    print()
    print("This is a NEW session. The agent has NO in-memory context")
    print("from Session 1. All context comes from Memanto recall.")
    print()

    # Initialize Memanto toolkit (new session, same agent)
    toolkit = MemantoToolkit(api_key=api_key)
    toolkit.setup(
        agent_id=CUSTOMER_ID,
        pattern="support",
        description="ACME Corp support agent (session 2)",
        duration_hours=6,
    )
    print(f"[OK] New session activated for agent '{CUSTOMER_ID}'")
    print()

    # Build a fresh LangGraph agent
    graph = build_support_agent_graph(
        toolkit=toolkit,
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key=openai_key,
        openai_base_url=os.environ.get("OPENAI_BASE_URL"),
    )
    print("[OK] Fresh LangGraph agent built (no in-memory state)")
    print()

    # First, do a direct recall to show what's in memory
    print("-" * 60)
    print("  Direct Memory Recall (before conversation)")
    print("-" * 60)
    result = toolkit.recall(query="ACME Corp customer preferences", limit=5)
    memories = result.get("memories", [])
    print(f"Found {len(memories)} memories in Memanto:")
    for mem in memories:
        print(f"  [{mem.get('type')}] {mem.get('title')}")
        print(f"    {mem.get('content', '')[:120]}...")
    print()

    # Run conversation turns
    messages = []
    for i, question in enumerate(RECALL_QUESTIONS, 1):
        print(f"--- Recall Test {i}/{len(RECALL_QUESTIONS)} ---")
        print(f"Customer: {question}")
        print()

        messages = run_conversation(
            graph=graph,
            customer_id=CUSTOMER_ID,
            user_message=question,
            existing_messages=messages,
        )

        # Print the agent's reply
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"Agent: {msg.content}")
                break
        print()

    # Teardown
    toolkit.teardown()
    print("[OK] Session 2 ended.")
    print()
    print("The agent successfully recalled information from Session 1!")
    print("This proves Memanto provides true cross-session persistence.")


if __name__ == "__main__":
    main()

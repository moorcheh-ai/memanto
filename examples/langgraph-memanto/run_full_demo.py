#!/usr/bin/env python3
"""
Full Demo: LangGraph + Memanto Customer Support Agent

Runs the complete demo in a single script:
  1. Session 1: Agent interacts with customer, learns preferences
  2. Session 2: New session, agent recalls prior context
  3. RAG Answer: Direct question-answering over stored memories

This is the recommended script for recording the demo GIF/video.

Usage:
    python run_full_demo.py
"""

from __future__ import annotations

import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CUSTOMER_ID = "customer-acme-001"


def separator(title: str) -> None:
    """Print a section separator."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def main() -> None:
    """Run the full demo."""
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

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("OPENAI_BASE_URL")

    # ------------------------------------------------------------------
    # PHASE 1: Store customer context
    # ------------------------------------------------------------------
    separator("PHASE 1: Customer Onboarding (Store Context)")

    toolkit = MemantoToolkit(api_key=api_key)
    toolkit.setup(
        agent_id=CUSTOMER_ID,
        pattern="support",
        description="ACME Corp support agent",
        duration_hours=6,
    )
    print(f"[OK] Agent '{CUSTOMER_ID}' activated\n")

    graph1 = build_support_agent_graph(
        toolkit=toolkit, model=model,
        openai_api_key=openai_key, openai_base_url=base_url,
    )

    session1_turns = [
        "Hi, I'm Jane from ACME Corp. We're on the Enterprise plan.",
        "We prefer CSV format for reports — our finance team finds JSON hard to work with.",
        "We had rate limiting issues during 9-11 AM EST last month. It was fixed by increasing our quota.",
        "Our account manager is Bob Williams. We'd like to keep him.",
    ]

    messages = []
    for i, turn in enumerate(session1_turns, 1):
        print(f"  [{i}/{len(session1_turns)}] Customer: {turn}")
        messages = run_conversation(graph1, CUSTOMER_ID, turn, messages)
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"  Agent: {msg.content[:150]}...")
                break
        print()

    toolkit.teardown()
    print("[OK] Session 1 ended. Teardown complete.")
    time.sleep(1)

    # ------------------------------------------------------------------
    # PHASE 2: Cross-session recall
    # ------------------------------------------------------------------
    separator("PHASE 2: New Session — Cross-Session Recall")

    toolkit2 = MemantoToolkit(api_key=api_key)
    toolkit2.setup(
        agent_id=CUSTOMER_ID,
        pattern="support",
        description="ACME Corp support agent (session 2)",
        duration_hours=6,
    )
    print(f"[OK] NEW session for '{CUSTOMER_ID}' (no in-memory state)\n")

    graph2 = build_support_agent_graph(
        toolkit=toolkit2, model=model,
        openai_api_key=openai_key, openai_base_url=base_url,
    )

    recall_questions = [
        "Hey, it's Jane again. What report format do we prefer?",
        "Who is our account manager?",
    ]

    messages2 = []
    for i, q in enumerate(recall_questions, 1):
        print(f"  [{i}/{len(recall_questions)}] Customer: {q}")
        messages2 = run_conversation(graph2, CUSTOMER_ID, q, messages2)
        for msg in reversed(messages2):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"  Agent: {msg.content[:200]}...")
                break
        print()

    # ------------------------------------------------------------------
    # PHASE 3: RAG Answer
    # ------------------------------------------------------------------
    separator("PHASE 3: Direct RAG Answer")

    answer = toolkit2.answer(
        question="Summarize everything we know about ACME Corp's setup, preferences, and history."
    )
    print(f"  Q: Summarize ACME Corp's setup and history")
    print(f"  A: {answer.get('answer', 'No answer')}")
    print()

    toolkit2.teardown()
    separator("DEMO COMPLETE")
    print("Memanto provided persistent, cross-session memory for the LangGraph agent.")
    print("All customer context survived across sessions and was used to personalize responses.")


if __name__ == "__main__":
    main()

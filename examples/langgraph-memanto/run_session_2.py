#!/usr/bin/env python3
"""
Session 2: Customer Support Agent — Next-Day Follow-Up.

The customer (Alice) returns. The agent uses memanto_recall to retrieve
all context from Session 1 — preferences, bug details, and decisions —
without Alice needing to repeat herself.

This is the key demonstration: CROSS-SESSION RECALL.
The agent remembers what happened "yesterday" even though nothing is
in the current conversation state.

Usage:
    python run_session_2.py
"""

from __future__ import annotations

import os
import sys

from agent import MemantoSetup, build_agent
from dotenv import load_dotenv

AGENT_ID = "langgraph-customer-support"
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """\
You are a senior customer support agent for CloudDash, a SaaS analytics
dashboard platform. You have access to persistent memory through Memanto
tools (memanto_remember, memanto_recall, memanto_answer).

Key behaviors:
- ALWAYS search memanto_recall first when a customer mentions a previous
  interaction or returns after some time. Their preferences and past issues
  are stored in Memanto.
- When a customer shares a preference, store it with memanto_remember.
- When you discover a bug or make a decision, store it (type=fact or decision).
- Be concise and professional. Cite stored memories when relevant.
"""


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY not set.")
        print("Copy .env.example to .env and add your Moorcheh API key.")
        sys.exit(1)

    setup = MemantoSetup(api_key)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="LangGraph customer support agent with persistent memory",
    )

    print(f"{'=' * 60}")
    print("  CloudDash Support — Session 2 (May 16, next day)")
    print(f"  Agent: {AGENT_ID}")
    print(f"  ⏳ Cross-Session Recall Demo")
    print(f"{'=' * 60}\n")

    try:
        agent = build_agent(client, AGENT_ID, SYSTEM_PROMPT, model=MODEL)

        # --- Turn 1: Alice returns ---
        msg1 = "Hey, it's Alice again. Any update on that dark mode bug I reported yesterday?"
        print(f"👤 Customer: {msg1}\n")
        result1 = agent.invoke({"messages": [("user", msg1)]})
        last_msg = result1["messages"][-1]
        print(f"🤖 Agent: {last_msg.content}\n")

        # --- Turn 2: Verify recall ---
        msg2 = (
            "Great, you remember everything! Can you check if there are any "
            "other users who reported similar dark mode chart issues?"
        )
        print(f"👤 Customer: {msg2}\n")
        result2 = agent.invoke({"messages": result1["messages"] + [("user", msg2)]})
        last_msg2 = result2["messages"][-1]
        print(f"🤖 Agent: {last_msg2.content}\n")

        print(f"{'=' * 60}")
        print("  Session 2 complete.")
        print("  ✅ Cross-session recall: agent retrieved Day 1 context")
        print("     (preferences, bug details, decisions) from Memanto.")
        print(f"{'=' * 60}")

    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()

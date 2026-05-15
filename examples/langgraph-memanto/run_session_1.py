#!/usr/bin/env python3
"""
Session 1: Customer Support Agent — First Interaction.

A customer (Alice) reports a bug. The agent stores context, preferences,
and decisions in Memanto's persistent memory so they survive across sessions.

Usage:
    python run_session_1.py
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
- When a customer shares a preference, store it with memanto_remember
  (type=preference, high confidence).
- When you discover a bug or make a decision, store it (type=fact or decision).
- If the customer mentions past interactions, search with memanto_recall first.
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
    print("  CloudDash Support — Session 1 (May 15)")
    print(f"  Agent: {AGENT_ID}")
    print(f"{'=' * 60}\n")

    try:
        agent = build_agent(client, AGENT_ID, SYSTEM_PROMPT, model=MODEL)

        # --- Turn 1: Initial contact ---
        msg1 = (
            "Hi, I'm Alice. I've been using CloudDash for about 6 months "
            "and I always use dark mode. Today I noticed that when I switch "
            "to the 'Revenue Trends' dashboard, all the charts render as "
            "blank white boxes. It only happens in dark mode — light mode "
            "is fine. Can you help?"
        )
        print(f"👤 Customer: {msg1}\n")
        result1 = agent.invoke({"messages": [("user", msg1)]})
        last_msg = result1["messages"][-1]
        print(f"🤖 Agent: {last_msg.content}\n")

        # --- Turn 2: Follow-up detail ---
        msg2 = "I'm on Chrome 132, macOS. The dashboard has 4 chart widgets."
        print(f"👤 Customer: {msg2}\n")
        result2 = agent.invoke({"messages": result1["messages"] + [("user", msg2)]})
        last_msg2 = result2["messages"][-1]
        print(f"🤖 Agent: {last_msg2.content}\n")

        print(f"{'=' * 60}")
        print("  Session 1 complete. Memories stored in Memanto.")
        print("  Run run_session_2.py to demonstrate cross-session recall.")
        print(f"{'=' * 60}")

    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()

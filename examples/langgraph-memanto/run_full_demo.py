#!/usr/bin/env python3
"""
Full Demo: LangGraph + Memanto Cross-Session Memory.

Runs both sessions in sequence to demonstrate that memories stored in
Session 1 are retrieved in Session 2 via Memanto's persistent semantic
database.

Usage:
    python run_full_demo.py
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
- If the customer mentions past interactions, search with memanto_recall first
  — their history is in Memanto even across different sessions.
- Use memanto_answer to synthesize insights from multiple memories.
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

    # ── Session 1 ───────────────────────────────────────────────────
    client1 = setup.setup(
        agent_id=AGENT_ID,
        description="LangGraph customer support agent with persistent memory",
    )

    print(f"\n{'=' * 60}")
    print("  SESSION 1 — May 15: First contact")
    print(f"  Agent: {AGENT_ID}")
    print(f"{'=' * 60}\n")

    agent1 = build_agent(client1, AGENT_ID, SYSTEM_PROMPT, model=MODEL)

    msg = (
        "Hi, I'm Alice. I've been using CloudDash for about 6 months "
        "and I always use dark mode. Today I noticed that when I switch "
        "to the 'Revenue Trends' dashboard, all the charts render as "
        "blank white boxes. It only happens in dark mode. I'm on "
        "Chrome 132, macOS. Can you help?"
    )
    print(f"👤 Alice: {msg}\n")
    result = agent1.invoke({"messages": [("user", msg)]})
    print(f"🤖 Agent: {result['messages'][-1].content}\n")

    setup.teardown(AGENT_ID)
    print("(Session 1 ended — agent deactivated)\n")

    # ── Session 2 ───────────────────────────────────────────────────
    print(f"{'=' * 60}")
    print("  SESSION 2 — May 16: Next day, new session")
    print(f"  ⏳ Nothing is in conversation state — will agent remember?")
    print(f"{'=' * 60}\n")

    client2 = setup.setup(agent_id=AGENT_ID)

    agent2 = build_agent(client2, AGENT_ID, SYSTEM_PROMPT, model=MODEL)

    msg2 = "Hey, it's Alice again. Any update on that dark mode chart bug I reported yesterday?"
    print(f"👤 Alice: {msg2}\n")
    result2 = agent2.invoke({"messages": [("user", msg2)]})
    print(f"🤖 Agent: {result2['messages'][-1].content}\n")

    setup.teardown(AGENT_ID)

    print(f"{'=' * 60}")
    print("  ✅ Full Demo Complete")
    print(f"  Cross-session recall: Agent retrieved Day 1 context")
    print(f"  from Memanto — without Alice repeating herself.")
    print(f"  Agent ID: {AGENT_ID}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

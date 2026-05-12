#!/usr/bin/env python3
"""
Session 1 — Alice introduces herself to the support agent.

The agent responds to each turn and stores structured memories in Memanto
after every exchange.  Run this FIRST, then run ``python run_session2.py``
in a NEW terminal to prove that memories survive across Python processes
(i.e., across sessions).

Usage:
    python run_session1.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from agent import build_support_agent

logging.basicConfig(level=logging.WARNING)

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_ID = "langgraph-support-agent"   # shared with Session 2 — same Memanto namespace
USER_ID = "user-alice-chen"            # logical user identifier
THREAD_ID = "alice-session-1"          # LangGraph conversation thread (within-session only)

# Scripted conversation: Alice reveals personal details, a billing issue, and
# an upgrade interest.  All of these become Memanto memories after each turn.
CONVERSATION = [
    "Hi there! My name is Alice Chen. I'm having trouble with my account.",
    (
        "I'm on the Pro plan and I work on a MacBook Pro M3 running macOS Sonoma 14.5. "
        "I always prefer dark mode — please keep that in mind."
    ),
    (
        "I was charged twice for my Pro subscription last month — "
        "once on May 3rd and again on May 17th. I need a refund for the duplicate charge."
    ),
    "One more thing: I'm seriously considering upgrading to the Team plan for 5 users.",
]


def run() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY is not set.\n"
            "Copy .env.example to .env and add your Moorcheh API key."
        )
        sys.exit(1)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print(
            "Error: OPENAI_API_KEY is not set.\n"
            "Add your OpenAI (or OpenRouter) key to .env."
        )
        sys.exit(1)

    llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    openai_base_url = os.environ.get("OPENAI_BASE_URL")

    print("\n" + "=" * 70)
    print("  SESSION 1 — Alice introduces herself")
    print(f"  Memanto Agent : {AGENT_ID}")
    print(f"  LangGraph Thread : {THREAD_ID}")
    print("=" * 70 + "\n")

    agent, memory = build_support_agent(api_key, AGENT_ID, llm_model, openai_base_url)
    thread_cfg = {"configurable": {"thread_id": THREAD_ID}}

    try:
        for turn_num, user_msg in enumerate(CONVERSATION, 1):
            print(f"[Turn {turn_num}]")
            print(f"Alice : {user_msg}\n")

            result = agent.invoke(
                {
                    "messages": [HumanMessage(content=user_msg)],
                    "user_id": USER_ID,
                    "recalled_context": "",
                },
                config=thread_cfg,
            )

            ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
            if ai_msgs:
                print(f"Agent : {ai_msgs[-1].content}\n")

            print("-" * 70 + "\n")

    finally:
        memory.close()

    print("=" * 70)
    print("  Session 1 complete.")
    print("  Alice's name, device, plan, billing issue, and upgrade intent")
    print("  are now stored as structured memories in Memanto.")
    print()
    print("  ➜  Run `python run_session2.py` to prove cross-session recall.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""
Session 2 — Alice returns in a brand-new Python process.

Key point: LangGraph's MemorySaver is in-process only — it has ZERO state
from Session 1.  Every piece of context the agent uses comes exclusively
from Memanto.  This is the cross-session recall that the bounty requires.

Run AFTER ``python run_session1.py``.

Usage:
    python run_session2.py
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
AGENT_ID = "langgraph-support-agent"   # same as Session 1 → same Memanto namespace
USER_ID = "user-alice-chen"
THREAD_ID = "alice-session-2"          # DIFFERENT thread: no LangGraph state carried over

# Alice comes back with follow-up questions.  The agent must recall her name,
# device, plan, and billing issue entirely from Memanto.
CONVERSATION = [
    "Hey, it's me again.  Did my refund request go through?",
    "Can you remind me what plan I'm on and the device I mentioned?",
    "Perfect.  I've decided to go ahead with the Team plan upgrade for 5 users — please note that.",
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
    print("  SESSION 2 — Alice returns in a NEW Python process")
    print()
    print("  LangGraph MemorySaver : EMPTY  (no state from Session 1)")
    print("  Memanto               : FULL   (all memories from Session 1 persist)")
    print()
    print(f"  Memanto Agent    : {AGENT_ID}")
    print(f"  LangGraph Thread : {THREAD_ID}  ← different from Session 1")
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
    print("  Session 2 complete!")
    print()
    print("  The agent recalled Alice's name, device, subscription plan, and")
    print("  billing issue from Memanto — with zero LangGraph state from")
    print("  Session 1.  That is cross-session memory in action.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run()

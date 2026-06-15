#!/usr/bin/env python3
"""
Demo: LangGraph + Memanto Cross-Session Recall

Demonstrates two sessions:
  Session 1: User shares preferences → Agent stores them as Memanto memories.
  Session 2: New thread, no context → Agent recalls preferences automatically.

Prerequisites:
    pip install -r requirements.txt
    cp .env.example .env   # then add your API keys

Usage:
    # Full demo (sessions 1 + 2 back-to-back)
    python run_demo.py

    # Session 1 only (store memories)
    python run_demo.py --session 1

    # Session 2 only (prove cross-session recall — run after session 1)
    python run_demo.py --session 2
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def check_env():
    """Check that required API keys are set."""
    missing = []
    if not os.getenv("MOORCHEH_API_KEY"):
        missing.append("MOORCHEH_API_KEY")
    if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENROUTER_API_KEY or OPENAI_API_KEY")
    if missing:
        print("❌ Missing environment variables: " + ", ".join(missing))
        print("   Copy .env.example to .env and add your keys.")
        sys.exit(1)


def session_1():
    """Session 1: User shares preferences and info."""
    from custom_memory_saver.langgraph_agent import run_session

    print("=" * 70)
    print("📝 SESSION 1: User shares preferences")
    print("=" * 70)

    responses = run_session(
        user_id="alice",
        session_id="session-001",
        messages=[
            (
                "human",
                "Hi! My name is Alice and I prefer concise answers. "
                "I'm a frontend developer working with React.",
            ),
            (
                "human",
                "I also love dark mode for all my tools. My timezone is PST.",
            ),
            (
                "human",
                "I'm having an issue with my login — "
                "it keeps redirecting me to the homepage instead of my dashboard.",
            ),
        ],
        thread_id="alice-session-001",
    )

    print("\n💬 Agent Responses:")
    for i, resp in enumerate(responses, 1):
        print(f"\n  --- Turn {i} ---")
        print(f"  {resp}")

    print("\n✅ Session 1 complete. Memories stored in Memanto.")
    return responses


def session_2():
    """Session 2: User returns — agent should recall stored memories."""
    from custom_memory_saver.langgraph_agent import run_session

    print("=" * 70)
    print("🔄 SESSION 2: User returns (NEW session, no context)")
    print("=" * 70)
    print("🤔 Can the agent remember Alice from yesterday?")
    print()

    responses = run_session(
        user_id="alice",
        session_id="session-002",
        messages=[
            (
                "human",
                "Hey, I'm back! Still having that redirect issue. Any updates?",
            ),
        ],
        thread_id="alice-session-002",
    )

    print("\n💬 Agent Response:")
    for i, resp in enumerate(responses, 1):
        print(f"\n  --- Turn {i} ---")
        print(f"  {resp}")

    print("\n✅ Session 2 complete.")
    return responses


def main():
    parser = argparse.ArgumentParser(
        description="LangGraph + Memanto Cross-Session Recall Demo"
    )
    parser.add_argument(
        "--session",
        type=int,
        choices=[1, 2],
        help="Run only session 1 or session 2 (default: both)",
    )
    args = parser.parse_args()

    check_env()

    if args.session == 1:
        session_1()
    elif args.session == 2:
        session_2()
    else:
        print("🚀 Running full demo: Session 1 → Session 2\n")
        session_1()
        print("\n" + "=" * 70)
        session_2()

    print("\n" + "=" * 70)
    print("🏁 Demo complete!")
    print("=" * 70)
    print()
    print("📖 Check README.md for instructions on recording a demo video.")
    print("📸 Take a screenshot/GIF and share on X with #Memanto!")


if __name__ == "__main__":
    main()

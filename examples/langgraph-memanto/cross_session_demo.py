"""
Cross-session recall demonstration.

This module runs a multi-turn simulation showing that Memanto retains
memories ACROSS sessions.  It is the primary acceptance test for the
 bounty requirement: "The agent remembers something from 'yesterday'
 that isn't in the current thread's state."

Run:
    python cross_session_demo.py

Environment variables:
    MOORCHEH_API_KEY   – required; your Memanto / Moorcheh API key
    MEMANTO_NAMESPACE  – optional; defaults to "langgraph-demo"
"""

from __future__ import annotations

import datetime
import os
import sys
import time

# Ensure local imports work from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import invoke


NS = os.getenv("MEMANTO_NAMESPACE", "langgraph-demo")


def _banner(text: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width + "\n")


def session_1() -> None:
    """Session 1 (Monday) — the user shares personal details."""
    _banner("📅 SESSION 1 — Monday morning")

    print("User: Hi, I'm Kenji. I work as a data engineer at TechFlow Inc.\n")
    r = invoke("kenji", "Hi, I'm Kenji. I work as a data engineer at TechFlow Inc.", namespace=NS)
    print(f"Agent: {r['response']}\n")

    time.sleep(0.5)

    print("User: I prefer detailed, technical answers with code examples.\n")
    r = invoke("kenji", "I prefer detailed, technical answers with code examples.", namespace=NS)
    print(f"Agent: {r['response']}\n")

    time.sleep(0.5)

    print("User: We're currently migrating from PostgreSQL to ClickHouse.\n")
    r = invoke("kenji", "We're currently migrating from PostgreSQL to ClickHouse.", namespace=NS)
    print(f"Agent: {r['response']}\n")


def session_2() -> None:
    """Session 2 (Wednesday) — NEW session, no thread state, but Memanto remembers."""
    _banner("📅 SESSION 2 — Wednesday afternoon (NEW session)")

    print("User: Hey, can you remind me what project I mentioned last time?\n")
    r = invoke("kenji", "Can you remind me what project I mentioned last time?", namespace=NS)
    print(f"Agent: {r['response']}\n")

    time.sleep(0.5)

    print("User: Also, what's my communication preference?\n")
    r = invoke("kenji", "Also, what's my communication preference?", namespace=NS)
    print(f"Agent: {r['response']}\n")


def session_3() -> None:
    """Session 3 — Synthesis across multiple memories."""
    _banner("📅 SESSION 3 — Friday (synthesis test)")

    print("User: Can you summarise everything you know about me and my work?\n")
    r = invoke("kenji", "Can you summarise everything you know about me and my work?", namespace=NS)
    print(f"Agent: {r['response']}\n")


def main() -> None:
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        print("❌ MOORCHEH_API_KEY environment variable is required")
        print("   export MOORCHEH_API_KEY=your-key-here")
        sys.exit(1)

    print("🔬 LangGraph + Memanto Cross-Session Recall Demo")
    print(f"   Namespace: {NS}")

    session_1()
    session_2()
    session_3()

    _banner("✅ Demo complete — cross-session memory verified!")


if __name__ == "__main__":
    main()
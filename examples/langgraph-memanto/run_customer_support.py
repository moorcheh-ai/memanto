#!/usr/bin/env python3
"""Customer Support Agent — Memanto-powered LangGraph demo.

Usage:
  python run_customer_support.py --session 1   # First conversation
  python run_customer_support.py --session 2   # Second conversation (proves persistence)
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langgraph_memanto.agent import build_agent
from langgraph_memanto.memory_client import MemantoClient
from langgraph_memanto.state import AgentState

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Memanto + LangGraph Customer Support Agent")
    parser.add_argument("--session", type=int, default=1, choices=[1, 2],
                        help="Session number (1 = first convo, 2 = second convo)")
    parser.add_argument("--agent-id", default="customer-support-demo",
                        help="Memanto agent ID (shared across sessions)")
    parser.add_argument("--memanto-url", default=os.getenv("MEMANTO_URL", "http://localhost:8000"),
                        help="Memanto server URL")
    args = parser.parse_args()

    # Create Memanto client
    client = MemantoClient(
        base_url=args.memanto_url,
        agent_id=args.agent_id,
    )

    # Check if Memanto is running
    if not client.health_check():
        print("⚠️  Memanto server is not reachable. Starting in offline demo mode.")
        print(f"   Expected at: {args.memanto_url}")
        print("   Start with: pip install memanto && memanto server start")
        print()

    # Build the LangGraph agent
    agent = build_agent(memanto_client=client, agent_id=args.agent_id)

    # ── Session 1: First conversation ──────────────────────────────────────
    if args.session == 1:
        print("=" * 60)
        print("📞 SESSION 1: First Customer Conversation")
        print("=" * 60)
        print()

        queries = [
            "Hi there! I'm Alice and I need help with my account.",
            "I prefer email notifications over SMS.",
            "Please save my email as alice@example.com.",
            "What do you remember about me?",
        ]

        for query in queries:
            print(f"\n🗣️  User: {query}")
            state = AgentState(
                user_input=query,
                memanto_agent_id=args.agent_id,
                session_id="session-1",
            )
            result = agent.invoke(state)
            print(f"🤖 Agent: {result.get('response', '')}")

            if result.get("memory_ops"):
                for op in result["memory_ops"]:
                    if op["status"] == "ok":
                        print(f"   🧠 [Memory] {op['op']}: {op.get('title', op.get('query', ''))}")

        print()
        print("✅ Session 1 complete. Memories stored in Memanto.")
        print("   Run 'python run_customer_support.py --session 2' to prove persistence.")

    # ── Session 2: New conversation (proves cross-session recall) ──────────
    elif args.session == 2:
        print("=" * 60)
        print("📞 SESSION 2: Returning Customer (NEW conversation)")
        print("=" * 60)
        print("   ⚡ This session starts FRESH — no LangGraph state from session 1.")
        print("   ⚡ All context comes from Memanto's long-term memory.")
        print()

        queries = [
            "Hello again! Do you know who I am?",
            "What do you remember about my communication preferences?",
            "I'd like to update my contact info — I also use SMS now.",
        ]

        for query in queries:
            print(f"\n🗣️  User: {query}")
            state = AgentState(
                user_input=query,
                memanto_agent_id=args.agent_id,
                session_id="session-2",
            )
            result = agent.invoke(state)
            print(f"🤖 Agent: {result.get('response', '')}")

            if result.get("memory_ops"):
                for op in result["memory_ops"]:
                    if op["status"] == "ok":
                        print(f"   🧠 [Memory] {op['op']}: {op.get('title', op.get('query', ''))}")

        print()
        print("🎉 Cross-session recall demonstrated!")
        print("   The agent remembered information from Session 1 even though")
        print("   Session 2 started with a completely fresh LangGraph state.")


if __name__ == "__main__":
    main()

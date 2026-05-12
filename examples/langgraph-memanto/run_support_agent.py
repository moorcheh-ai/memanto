"""
Customer Support Agent — LangGraph + Memanto integration example.

Demonstrates a practical customer support agent that:
1. Remembers customer details across sessions
2. Recalls past issues and preferences
3. Synthesises information from multiple stored memories

Run:
    python run_support_agent.py

Environment variables:
    MOORCHEH_API_KEY   – required
    MEMANTO_NAMESPACE  – optional; defaults to "support-agent"
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import invoke

NS = os.getenv("MEMANTO_NAMESPACE", "support-agent")


def run_scenario(user_id: str, messages: list[str]) -> None:
    """Run a sequence of messages simulating a support conversation."""
    print(f"\n👤 Customer: {user_id}")
    print("-" * 50)

    for i, msg in enumerate(messages, 1):
        print(f"\n  [{i}] Customer: {msg}")
        result = invoke(user_id, msg, namespace=NS)
        print(f"  [{i}] Agent:    {result['response']}")


def main() -> None:
    if not os.getenv("MOORCHEH_API_KEY"):
        print("❌ MOORCHEH_API_KEY environment variable is required")
        sys.exit(1)

    print("🎯 Customer Support Agent — LangGraph + Memanto Demo\n")

    # Scenario 1: New customer reports an issue and shares preferences
    run_scenario(
        "customer_alice",
        [
            "Hi, I'm Alice. I recently signed up for your Enterprise plan.",
            "I'm having trouble with API rate limits — I'm getting 429 errors even though my plan says unlimited.",
            "Please give me short, actionable answers — I'm very busy.",
        ],
    )

    # Scenario 2: Same customer returns a week later (cross-session recall)
    run_scenario(
        "customer_alice",
        [
            "Hey, I'm back. Do you remember what issue I reported last time?",
            "Is the rate limit problem resolved?",
        ],
    )

    print("\n✅ Customer support demo complete!")


if __name__ == "__main__":
    main()
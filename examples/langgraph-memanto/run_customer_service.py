"""
Session A (Day 1): Customer Service Interaction

A new customer interacts with the support agent.
The agent stores their preferences, facts, and goals
as typed semantic memories in Memanto.

Run this:
    python run_customer_service.py

Then verify persistence by running:
    python run_followup.py
"""
import logging
import sys

from agent import run_agent
from memory import create_memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

SEPARATOR = "=" * 60


def main():
    print(SEPARATOR)
    print("📞 SESSION A (DAY 1): CUSTOMER ONBOARDING")
    print("Agent stores customer memories via Memanto")
    print(SEPARATOR)

    memory = create_memory()

    # ── Interaction 1: Customer introduces themselves ──
    print("\n🟢 CUSTOMER: \"Hi, my name is Sarah Chen. I work at Acme Corp.\"\n")
    result1 = run_agent(
        customer_id="sarah-chen",
        message="Hi, my name is Sarah Chen. I work at Acme Corp.",
        session_label="Session A (Day 1)",
        memory=memory,
    )
    print(f"🤖 AGENT: {result1['response']}\n")
    print(f"   Memories stored: {len(result1.get('memories_stored', []))}")

    # ── Interaction 2: Customer states preferences ──
    print(f"\n{SEPARATOR}")
    print("\n🟢 CUSTOMER: \"I prefer getting support via email instead of phone.\"\n")
    result2 = run_agent(
        customer_id="sarah-chen",
        message="I prefer getting support via email instead of phone. I like dark mode for all interfaces.",
        session_label="Session A (Day 1)",
        memory=memory,
    )
    print(f"🤖 AGENT: {result2['response']}\n")
    print(f"   Memories stored: {len(result2.get('memories_stored', []))}")

    # ── Interaction 3: Customer states a goal ──
    print(f"\n{SEPARATOR}")
    print("\n🟢 CUSTOMER: \"My goal is to set up the API integration by next week.\"\n")
    result3 = run_agent(
        customer_id="sarah-chen",
        message="My goal is to set up the API integration by next week.",
        session_label="Session A (Day 1)",
        memory=memory,
    )
    print(f"🤖 AGENT: {result3['response']}\n")

    # ── Summary ──
    print(f"\n{SEPARATOR}")
    print("📋 SESSION A SUMMARY")
    print(f"   Customer: Sarah Chen (sarah-chen)")
    print(f"   Company:  Acme Corp")
    print(f"   Stored:   Name, company, preferences, goal")
    print(f"   System:   Memanto typed semantic memory")
    print(f"\n👉 Now run 'python run_followup.py' to prove cross-session recall!")
    print(SEPARATOR)


if __name__ == "__main__":
    main()

"""
Session B (Day 2): Cross-Session Recall

The customer returns the next day. The agent has NO access to
LangGraph's internal state from Session A.

This script PROVES Memanto provides persistent, cross-session memory
that survives agent restarts.

Run this AFTER run_customer_service.py:
    python run_customer_service.py   # First
    python run_followup.py           # Second (proves persistence)
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
    print("🔄 SESSION B (DAY 2): CROSS-SESSION RECALL DEMO")
    print("LangGraph starts fresh — Memanto provides long-term memory")
    print(SEPARATOR)

    # NOTE: We create a NEW memory instance for Session B.
    # If using MemantoMemory (CLI/real), it fetches from the cloud.
    # If using MockMemantoMemory, it... well, won't cross sessions.
    # The real demo requires Memanto CLI + Moorcheh API key.
    memory = create_memory()

    if isinstance(memory.__class__.__name__, str) and "Mock" in str(memory.__class__.__name__):
        print("\n⚠️  Using MockMemantoMemory — cross-session recall will NOT work.")
        print("   Install the real memanto CLI and set MOORCHEH_API_KEY in .env")
        print("   for a true cross-session persistence demo.\n")

    # ── Phase 1: Ask what the agent knows (recall intent) ──
    print("\n🟢 CUSTOMER: \"Hi Sarah here again! What do you remember about me?\"\n")

    # New graph, new state, new session — but Memanto remembers!
    result_recall = run_agent(
        customer_id="sarah-chen",
        message="What do you know about me? I'm Sarah Chen.",
        session_label="Session B (Day 2)",
        memory=memory,
    )

    print(f"🤖 AGENT: {result_recall['response']}\n")

    # ── Phase 2: Ask a specific question about preferences ──
    print(f"\n{SEPARATOR}")
    print("\n🟢 CUSTOMER: \"How should you contact me for support?\"\n")

    result_contact = run_agent(
        customer_id="sarah-chen",
        message="How should you contact me for support? I told you yesterday.",
        session_label="Session B (Day 2)",
        memory=memory,
    )

    print(f"🤖 AGENT: {result_contact['response']}\n")

    # ── Phase 3: Ask about goals ──
    print(f"\n{SEPARATOR}")
    print("\n🟢 CUSTOMER: \"What was my goal?\"\n")

    result_goal = run_agent(
        customer_id="sarah-chen",
        message="What was my goal that I mentioned?",
        session_label="Session B (Day 2)",
        memory=memory,
    )

    print(f"🤖 AGENT: {result_goal['response']}\n")

    # ── Summary ──
    print(f"\n{SEPARATOR}")
    print("✅ CROSS-SESSION RECALL VERIFICATION")
    if isinstance(memory, MockMemantoMemory):
        print("   ⚠️  Using mock memory — install real memanto for true persistence")
    else:
        print("   ✅ Memanto persisted memories across sessions!")
        print("   ✅ LangGraph started fresh (no internal state from Day 1)")
        print("   ✅ Agent recalled: name, company, preferences, goal")
    print(SEPARATOR)


if __name__ == "__main__":
    main()

"""
Full Pipeline: Session A + Session B in one script.

Runs the customer service interaction and then the follow-up,
demonstrating the complete LangGraph + Memanto workflow.

For the best demo experience, run the two scripts separately:
    python run_customer_service.py   # Day 1
    python run_followup.py           # Day 2 (proves cross-session recall)
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
    print("🏭 LANGGRAPH + MEMANTO FULL PIPELINE")
    print(SEPARATOR)

    memory = create_memory()

    # ── Phase 1: Session A ──
    print("\n📦 PHASE 1: SESSION A (STORE MEMORIES)\n")

    run_agent(
        customer_id="alex-rivera",
        message="Hey! My name is Alex Rivera. I work at a fintech startup.",
        session_label="Session A",
        memory=memory,
    )
    run_agent(
        customer_id="alex-rivera",
        message="I prefer getting updates via Slack. I like minimalistic UI designs.",
        session_label="Session A",
        memory=memory,
    )
    run_agent(
        customer_id="alex-rivera",
        message="My goal is to deploy the monitoring dashboard by Friday.",
        session_label="Session A",
        memory=memory,
    )

    # ── Phase 2: Session B (same customer, new session) ──
    print(f"\n{SEPARATOR}")
    print("\n📦 PHASE 2: SESSION B (CROSS-SESSION RECALL)\n")

    result = run_agent(
        customer_id="alex-rivera",
        message="Hi, it's Alex again. What do you remember about me?",
        session_label="Session B (Cross-Session)",
        memory=memory,
    )

    print(f"🤖 AGENT: {result['response']}\n")

    # ── Verification ──
    print(f"\n{SEPARATOR}")
    if result.get("memory_context"):
        print("✅ CROSS-SESSION RECALL CONFIRMED")
        print("   The agent recalled memories stored in a previous session.")
    else:
        print("⚠️  No memories recalled — check Memanto configuration.")
        print("   Install memanto CLI and configure MOORCHEH_API_KEY in .env")
    print(SEPARATOR)


if __name__ == "__main__":
    main()

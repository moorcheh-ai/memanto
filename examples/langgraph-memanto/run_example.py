"""
Run a two-session demonstration of the LangGraph + Memanto customer support agent.

Session 1: Customer reports a billing issue
Session 2: Customer follows up the next day - agent recalls prior issue from Memanto
"""

import os
from dotenv import load_dotenv

from agent import (
    AGENT_ID,
    MemantoMemoryManager,
    build_support_graph,
    run_session,
)

load_dotenv()


def main():
    # Initialize Memanto memory manager
    api_key = os.environ.get("MEMANTO_API_KEY", "")
    if not api_key:
        print("Error: MEMANTO_API_KEY environment variable is required")
        print("Set it in .env or export it before running.")
        return

    memory = MemantoMemoryManager(api_key=api_key, agent_id=AGENT_ID)

    # Setup: create agent and activate session
    memory.setup(duration_hours=2)

    # Build the LangGraph workflow
    graph = build_support_graph(memory=memory)

    # Session 1: Customer reports a billing issue
    run_session(
        graph=graph,
        memory=memory,
        customer_message="Hi, I was charged twice for my subscription last month. Order #12345.",
        session_label="Session 1 - Initial Report",
    )

    # Session 2: Customer follows up (next day, no shared thread state)
    # The agent should recall the billing issue from Memanto
    run_session(
        graph=graph,
        memory=memory,
        customer_message="Hey, I am following up on the billing issue I reported yesterday.",
        session_label="Session 2 - Follow-up (cross-session recall)",
    )

    # Cleanup
    memory.teardown()

    print("
" + "=" * 60)
    print("Demo complete! Session 2 recalled context from Session 1")
    print("without any shared LangGraph thread state.")
    print("=" * 60)


if __name__ == "__main__":
    main()

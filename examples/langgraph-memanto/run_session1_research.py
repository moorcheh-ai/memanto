#!/usr/bin/env python3
"""
Session 1: Research Phase

The research assistant explores a topic and stores its findings
in Memanto's persistent memory. These memories will be available
in Session 2 — even though it's a completely separate invocation.

Usage:
    python run_session1_research.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from research_assistant import build_research_graph  # noqa: E402
from memanto_langgraph import MemantoSetup  # noqa: E402


def main() -> None:
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("❌ Set MOORCHEH_API_KEY in .env first.")
        sys.exit(1)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Set OPENAI_API_KEY in .env first.")
        sys.exit(1)

    agent_id = "research-assistant"

    print("🔬 Research Assistant — Session 1: Research Phase")
    print("=" * 60)

    # 1. Set up Memanto
    print("\n📚 Setting up Memanto agent...")
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id=agent_id, description="LangGraph research assistant")
    print(f"✅ Agent '{agent_id}' ready")

    # 2. Build graph
    graph, saver = build_research_graph(client, agent_id=agent_id)

    # 3. Research queries — the agent will store findings in Memanto
    research_queries = [
        "Research the top 3 trends in quantum computing for 2025. "
        "For each trend, store it as a separate memory using memanto_remember "
        "with memory_type='fact' and appropriate tags. "
        "Also remember that the user is particularly interested in "
        "quantum error correction.",

        "What are the main challenges in building practical quantum computers? "
        "Store the key challenges as memories with memory_type='observation'. "
        "Also store a preference memory that the user wants to track "
        "breakthroughs in topological qubits.",
    ]

    for i, query in enumerate(research_queries, 1):
        print(f"\n{'─' * 60}")
        print(f"📝 Research Query {i}: {query[:80]}...")
        print(f"{'─' * 60}")

        result = graph.invoke(
            {
                "messages": [("human", query)],
                "past_context": "",
                "mode": "research",
            },
            config={"recursion_limit": 15},
        )

        # Print the final assistant response
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                print(f"\n🤖 Assistant: {msg.content[:500]}")
                break

    # 4. Save a summary interaction
    print(f"\n{'─' * 60}")
    print("💾 Saving session summary to Memanto...")
    saver.save_interaction(
        user_message="Completed research session on quantum computing trends and challenges",
        assistant_reply="Stored 5 memories: 3 trend facts, 2 challenge observations, and 2 user preferences",
        metadata={"turn": "session1-summary"},
    )

    print("\n✅ Session 1 complete!")
    print("   → Memories persisted to Memanto")
    print("   → Run Session 2 to prove cross-session recall:")
    print("     python run_session2_recall.py")


if __name__ == "__main__":
    main()

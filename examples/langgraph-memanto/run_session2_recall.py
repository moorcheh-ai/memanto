#!/usr/bin/env python3
"""
Session 2: Recall Phase (Proves Cross-Session Memory!)

A completely new invocation that loads context from Memanto and
demonstrates the agent remembers findings from Session 1 — even
though Session 1's conversation state is NOT in this process.

Usage:
    python run_session2_recall.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from memanto_langgraph import MemantoSetup  # noqa: E402
from research_assistant import build_research_graph  # noqa: E402


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

    print("🧠 Research Assistant — Session 2: Recall Phase")
    print("=" * 60)
    print("   (This is a NEW invocation — no Session 1 state exists here!)")

    # 1. Set up Memanto (same agent_id → same memory namespace)
    print("\n📖 Setting up Memanto and loading past context...")
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id=agent_id)

    # 2. Build graph
    graph, saver = build_research_graph(client, agent_id=agent_id)

    # 3. Load context from past sessions — THIS is the cross-session magic
    past_context = saver.load_context(
        query="quantum computing research findings and user preferences"
    )

    if past_context:
        print(f"\n✅ Loaded {len(past_context.splitlines())} lines of context from past sessions")
        print(f"   Preview: {past_context[:200]}...")
    else:
        print("\n⚠️  No past context found. Did you run Session 1 first?")
        print("   Run: python run_session1_research.py")
        sys.exit(1)

    # 4. Recall queries — the agent uses past-session memories
    recall_queries = [
        "What quantum computing trends did we research in our previous session?",
        "What was I particularly interested in regarding quantum computing?",
        "Based on our past research, what are the biggest challenges in quantum computing?",
    ]

    for i, query in enumerate(recall_queries, 1):
        print(f"\n{'─' * 60}")
        print(f"💬 Query {i}: {query}")
        print(f"{'─' * 60}")

        result = graph.invoke(
            {
                "messages": [("human", query)],
                "past_context": past_context,
                "mode": "recall",
            },
            config={"recursion_limit": 10},
        )

        # Print the final assistant response
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                print(f"\n🤖 Assistant: {msg.content}")
                break

    print(f"\n{'=' * 60}")
    print("✅ Cross-session recall demonstrated!")
    print("   → The agent answered questions about Session 1's research")
    print("   → Memories were loaded from Memanto, not from conversation history")
    print("   → This proves persistent cross-session memory!")


if __name__ == "__main__":
    main()

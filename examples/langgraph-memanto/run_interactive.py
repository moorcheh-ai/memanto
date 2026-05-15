#!/usr/bin/env python3
"""
Interactive Research Assistant with Persistent Memory

A continuous chat that demonstrates cross-session memory persistence.
Memories are automatically saved to Memanto after each turn and loaded
at the start of every new session.

Usage:
    python run_interactive.py
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

    print("🔬 Research Assistant — Interactive Mode")
    print("=" * 60)
    print("  • Stores findings in Memanto after each turn")
    print("  • Loads context from past sessions automatically")
    print("  • Type 'quit' to exit")
    print("  • Type 'memories' to see stored memories")
    print("=" * 60)

    # 1. Set up Memanto
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id=agent_id, description="LangGraph research assistant")

    # 2. Build graph
    graph, saver = build_research_graph(client, agent_id=agent_id)

    # 3. Load past context
    past_context = saver.load_context(
        query="all research findings, facts, preferences, and goals"
    )

    if past_context:
        print(f"\n📖 Loaded memories from past sessions ({len(past_context)} chars)")
    else:
        print("\n📝 No past memories found — starting fresh!")

    # 4. Chat loop
    turn = 0
    while True:
        try:
            user_input = input("\n💬 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("👋 Goodbye!")
            break

        if user_input.lower() == "memories":
            result = saver._client.recall(
                agent_id=agent_id,
                query="all stored memories",
                limit=20,
            )
            memories = result.get("memories", [])
            if memories:
                print(f"\n📚 Stored Memories ({len(memories)}):")
                for i, mem in enumerate(memories, 1):
                    print(f"  {i}. [{mem.get('type')}] {mem.get('title')}")
            else:
                print("\n📚 No memories stored yet.")
            continue

        turn += 1

        # Invoke graph
        result = graph.invoke(
            {
                "messages": [("human", user_input)],
                "past_context": past_context,
                "mode": "interactive",
            },
            config={"recursion_limit": 15},
        )

        # Print response
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                print(f"\n🤖 Assistant: {msg.content}")
                break

        # Save interaction to Memanto
        assistant_reply = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                assistant_reply = msg.content
                break

        saver.save_interaction(
            user_message=user_input,
            assistant_reply=assistant_reply,
            metadata={"turn": turn},
        )

        # Refresh context for next turn
        past_context = saver.load_context(
            query="all research findings, facts, preferences, and goals"
        )


if __name__ == "__main__":
    main()

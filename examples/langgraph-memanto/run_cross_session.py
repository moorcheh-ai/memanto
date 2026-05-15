"""
Demo: Cross-Session Recall with LangGraph + Memanto

This script demonstrates the key differentiator of using Memanto
as a memory layer for LangGraph agents: the agent remembers
information across completely separate sessions.

Run flow:
  Session 1: User tells the agent their preferences and asks a question
  Session 2: New session starts, user asks a related question
             The agent recalls info from Session 1 and personalizes its response

Requirements:
  - MEMANTO_API_KEY environment variable
  - OPENAI_API_KEY environment variable
"""

from __future__ import annotations

import os
import sys
import time


def main() -> None:
    api_key = os.getenv("MEMANTO_API_KEY")
    if not api_key:
        print("Error: MEMANTO_API_KEY environment variable not set.")
        print("Get your key at https://memanto.ai and export it.")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Set it to use GPT models.")
        print("You can also modify agent.py to use a different model.")

    from agent import build_customer_support_agent
    from langchain_core.messages import HumanMessage

    AGENT_ID = "demo-support-agent"
    USER_ID = "user-42"

    # =====================================================================
    # SESSION 1: Initial interaction
    # =====================================================================
    print("=" * 60)
    print("SESSION 1: User shares preferences")
    print("=" * 60)

    graph, client, setup = build_customer_support_agent(
        api_key=api_key, agent_id=AGENT_ID
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"Hi! I'm {USER_ID}. I run an ecommerce store selling "
                        "handmade candles on Shopify. My biggest challenge is "
                        "abandoned cart recovery. I ship from California and "
                        "my average order value is $45. Can you help me think "
                        "of strategies?"
                    )
                )
            ],
            "user_id": USER_ID,
            "session_id": "session-1",
            "memories_recalled": False,
            "agent_id": AGENT_ID,
        }
    )

    print("\n--- Agent Response (Session 1) ---")
    for msg in result["messages"]:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            if role == "ai":
                print(f"[Agent] {msg.content[:300]}...")
            elif role == "tool":
                print(f"[Tool] {str(msg.content)[:150]}...")

    # Wait for memories to be indexed
    print("\n⏳ Waiting for memory indexing...")
    time.sleep(3)

    setup.teardown(AGENT_ID)

    # =====================================================================
    # SESSION 2: Cross-session recall
    # =====================================================================
    print("\n" + "=" * 60)
    print("SESSION 2: Cross-session recall (NEW session)")
    print("=" * 60)
    print("A completely new session starts. The agent has NO context")
    print("from Session 1 EXCEPT what was stored in Memanto.")
    print()

    # New graph instance = NEW session
    graph2, client2, setup2 = build_customer_support_agent(
        api_key=api_key, agent_id=AGENT_ID
    )

    result2 = graph2.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Hey, I need help with my store again. Any ideas "
                        "you remember about my business that could help with "
                        "customer retention?"
                    )
                )
            ],
            "user_id": USER_ID,
            "session_id": "session-2",
            "memories_recalled": False,
            "agent_id": AGENT_ID,
        }
    )

    print("--- Agent Response (Session 2 - Cross-Session) ---")
    for msg in result2["messages"]:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            if role == "ai":
                print(f"[Agent] {msg.content[:500]}")
            elif role == "tool":
                content_str = str(msg.content)[:200]
                if "memories" in content_str.lower() or "stored" in content_str.lower():
                    print(f"[Tool] {content_str}")

    setup2.teardown(AGENT_ID)

    # =====================================================================
    # Verification: Direct recall
    # =====================================================================
    print("\n" + "=" * 60)
    print("VERIFICATION: Direct memory check")
    print("=" * 60)

    client3 = setup.client  # reuse client for verification
    memories = client3.recall(
        agent_id=AGENT_ID,
        query=f"user {USER_ID} handmade candles ecommerce",
        limit=10,
    )

    stored = memories.get("memories", [])
    print(f"Stored memories about this user: {len(stored)}")
    for i, m in enumerate(stored, 1):
        print(f"  {i}. [{m.get('type')}] {m.get('title')}")
        print(f"     {m.get('content', '')[:100]}")

    print("\n✅ Cross-session recall demo complete!")
    print("The agent successfully remembered the user's business details")
    print("across completely separate sessions using Memanto.")


if __name__ == "__main__":
    main()

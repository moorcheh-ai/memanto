#!/usr/bin/env python3
"""
Customer Support Agent with Memanto Long-Term Memory

This example demonstrates a LangGraph agent that:
  1. Classifies the user's intent (technical, billing, feature, chat)
  2. Recalls previous memories for that user from Memanto
  3. Generates a context-aware response
  4. Stores new facts back into Memanto so they survive across sessions

Usage:
    export MOORCHEH_API_KEY="your-key"
    export OPENROUTER_API_KEY="your-key"   # free models available
    python run_customer_support.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph_memanto.client import MemantoSetup
from langgraph_memanto.graph import MemantoState, build_customer_support_graph

AGENT_ID = "langgraph-customer-support"
USER_ID = "demo-user-42"


def main() -> None:
    load_dotenv()

    moorcheh_key = os.environ.get("MOORCHEH_API_KEY")
    if not moorcheh_key:
        print("Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if not openrouter_key:
        print("Error: OPENROUTER_API_KEY not set. Get a free key at https://openrouter.ai/keys")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Set up Memanto
    # ------------------------------------------------------------------
    setup = MemantoSetup(api_key=moorcheh_key)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Customer support agent with persistent user memory",
    )

    # ------------------------------------------------------------------
    # 2. Configure LLM (OpenRouter free tier)
    # ------------------------------------------------------------------
    llm = ChatOpenAI(
        model="openrouter/tencent/hy3-preview:free",
        openai_api_base="https://openrouter.ai/api/v1",
        api_key=openrouter_key,
        temperature=0.3,
    )

    # ------------------------------------------------------------------
    # 3. Build the graph
    # ------------------------------------------------------------------
    graph = build_customer_support_graph(
        llm=llm,
        client=client,
        agent_id=AGENT_ID,
    )

    # ------------------------------------------------------------------
    # 4. Interactive demo loop
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Memanto + LangGraph — Customer Support Agent")
    print("=" * 60)
    print("  Type your message and press Enter.")
    print("  Type 'quit' or 'exit' to finish.\n")

    state = MemantoState(user_id=USER_ID)

    try:
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"quit", "exit", "q"}:
                break

            state.messages.append(HumanMessage(content=user_input))
            result = graph.invoke(state)

            # Update state for the next turn
            state = MemantoState(**result)

            # Print the latest AI message
            for msg in reversed(state.messages):
                if isinstance(msg, AIMessage):
                    print(f"Agent: {msg.content}\n")
                    break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        setup.teardown(AGENT_ID)
        print("\nSession ended. Memories persisted in Memanto.")


if __name__ == "__main__":
    main()

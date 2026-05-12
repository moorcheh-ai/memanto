#!/usr/bin/env python3
"""
Session 2: A NEW session — the agent recalls memories from Session 1.

The agent has no in-memory context from Session 1, but Memanto provides
cross-session recall so the agent "remembers" the customer's preferences.

Run AFTER `run_session_1.py`.

Usage:
    python run_session_2.py
"""

import os
import sys

from agent import build_graph, recall
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from memanto.app.clients.sdk_client import SdkClient


def main() -> None:
    load_dotenv()

    moorcheh_key = os.environ.get("MOORCHEH_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not moorcheh_key or not openai_key:
        print("Error: Set MOORCHEH_API_KEY and OPENAI_API_KEY in .env")
        sys.exit(1)

    client = SdkClient(api_key=moorcheh_key)
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key)
    graph = build_graph(client, llm)

    customer_id = "demo-customer-001"

    print(f"\n{'=' * 60}")
    print("  SESSION 2 — New session, cross-session recall in action")
    print(f"  Customer ID : {customer_id}")
    print(f"{'=' * 60}\n")

    # Show what Memanto recalls before the conversation
    print(">> Memories retrieved from Memanto (cross-session):")
    memories = recall(client, customer_id, "customer preferences and location")
    print(memories)
    print()

    user_msg = "Hey, do you remember what city I'm in? Also, what's my UI preference?"
    print(f"User: {user_msg}")

    state = {
        "messages": [HumanMessage(content=user_msg)],
        "customer_id": customer_id,
        "past_memories": "",
        "new_memory_title": None,
        "new_memory_content": None,
    }
    result = graph.invoke(state)
    print(f"Agent: {result['messages'][-1].content}\n")
    print("Cross-session recall demonstrated! The agent remembered without any in-memory context.")


if __name__ == "__main__":
    main()

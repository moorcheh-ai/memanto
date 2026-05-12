#!/usr/bin/env python3
"""
Session 1: Customer interacts with the support agent.

The agent stores key facts about the customer in Memanto.
Run this script first, then run `run_session_2.py` in a NEW terminal
(or even a new day) to prove cross-session recall.

Usage:
    python run_session_1.py
"""

import os
import sys

from agent import build_graph, AGENT_ID, remember
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
    print("  SESSION 1 — Customer first contact")
    print(f"  Customer ID : {customer_id}")
    print(f"{'=' * 60}\n")

    # Seed a known fact so Session 2 can recall it
    remember(
        client,
        customer_id,
        title="Customer prefers dark mode",
        content="The customer explicitly stated they prefer dark mode in the UI.",
    )

    messages = [
        "Hi! I just upgraded to the Pro plan. I prefer dark mode and I'm based in Tokyo.",
        "Also, my billing email is different from my login email — is that okay?",
    ]

    state = {
        "messages": [],
        "customer_id": customer_id,
        "past_memories": "",
        "new_memory_title": None,
        "new_memory_content": None,
    }

    for user_msg in messages:
        print(f"User: {user_msg}")
        state["messages"] = state["messages"] + [HumanMessage(content=user_msg)]
        state = graph.invoke(state)
        reply = state["messages"][-1].content
        print(f"Agent: {reply}\n")
        if state.get("new_memory_title"):
            print(f"  [Memory stored] → {state['new_memory_title']}\n")

    print("Session 1 complete. Run `python run_session_2.py` to see cross-session recall.")


if __name__ == "__main__":
    main()

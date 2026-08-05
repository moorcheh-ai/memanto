#!/usr/bin/env python3
"""Session 1: Bob shares preferences. The graph stores them in Memanto.

Run this first. Then run ``run_session_2.py`` (separately, fresh process)
to prove cross-session recall - that script starts a brand new graph
thread but still recalls what Bob said here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from memanto_base_store.graph import build_support_graph, latest_assistant_text

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

AGENT_ID = "langgraph-customer-support"
USER_ID = "bob"
THREAD_ID = "session-1"

USER_MESSAGE = (
    "Hi! I'm Bob. A couple of things upfront so you know how to help me: "
    "I'm allergic to peanuts (severe - epi-pen level), and please always "
    "reach me by email at bob@example.com, never by phone."
)


async def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)
    if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        print(
            "Error: OPENROUTER_API_KEY or OPENAI_API_KEY not set. Get one at https://openrouter.ai/keys."
        )
        sys.exit(1)

    # MemantoStore inside build_support_graph automatically handles client creation/activation.
    bar = "=" * 64
    print(f"\n{bar}\n  Session 1 - user={USER_ID}, thread_id={THREAD_ID}\n{bar}\n")
    print(f"User: {USER_MESSAGE}\n")

    try:
        graph = build_support_graph(api_key=api_key)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=USER_MESSAGE)]},
            config={"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}},
        )
        print(f"Agent: {latest_assistant_text(result['messages'])}\n")
        print(
            f"{bar}\n"
            f"  Stored preferences/facts in Memanto under namespace=({USER_ID!r}, 'memories')\n"
            f"  Run `python run_session_2.py` (new process) to prove they persist.\n"
            f"{bar}\n"
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

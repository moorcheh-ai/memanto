#!/usr/bin/env python3
"""Session 2: NEW thread, but the agent still remembers Bob's allergy.

Run ``run_session_1.py`` first. Then run this. The thread_id is different,
so LangGraph's checkpointer has no history - if the agent skips peanuts
in its snack recommendations, that's MemantoStore proving cross-session
recall.
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
THREAD_ID = "session-2-fresh"  # different from session 1 on purpose

USER_MESSAGE = "What snacks would you recommend for a long road trip next weekend?"


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

    # MemantoStore automatically ensures the agent exists and activates a session.
    bar = "=" * 64
    print(f"\n{bar}\n  Session 2 - user={USER_ID}, thread_id={THREAD_ID}\n{bar}\n")
    print(
        "  Checkpointer state for this thread_id is EMPTY. Any user knowledge\n"
        "  the agent uses below comes from MemantoStore (cross-thread).\n"
    )
    print(f"User: {USER_MESSAGE}\n")

    try:
        graph = build_support_graph(api_key=api_key)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=USER_MESSAGE)]},
            config={"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}},
        )
        reply = latest_assistant_text(result["messages"])
        print(f"Agent: {reply}\n")

        peanut_safe = "peanut" not in reply.lower() or any(
            phrase in reply.lower()
            for phrase in ("avoid peanut", "no peanut", "skip peanut", "peanut-free")
        )
        print(
            f"{bar}\n"
            f"  Cross-session recall: "
            f"{'OK (agent honored peanut allergy)' if peanut_safe else 'CHECK MANUALLY'}\n"
            f"{bar}\n"
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

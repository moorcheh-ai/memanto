#!/usr/bin/env python3
"""Run Session 1 and Session 2 back-to-back in one process.

This is the script the README's demo GIF records. Both sessions reuse
the same Memanto agent but each uses a *different* LangGraph thread_id,
so cross-thread recall is what's being demonstrated, not within-thread
checkpoint replay.
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

USER_ID = "bob"

SESSION_1_THREAD = "session-1"
SESSION_1_MESSAGE = (
    "Hi! I'm Bob. A couple of things upfront so you know how to help me: "
    "I'm allergic to peanuts (severe - epi-pen level), and please always "
    "reach me by email at bob@example.com, never by phone."
)

SESSION_2_THREAD = "session-2-fresh"
SESSION_2_MESSAGE = "What snacks would you recommend for a long road trip next weekend?"


async def run_turn(graph, thread_id: str, message: str, user_id: str) -> str:
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
    )
    return latest_assistant_text(result["messages"])


async def main() -> None:
    load_dotenv()
    os.environ["MEMANTO_BACKEND"] = "cloud"

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY not set. Copy .env.example to .env.")
        sys.exit(1)
    if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        print(
            "Error: OPENROUTER_API_KEY or OPENAI_API_KEY not set. Get one at https://openrouter.ai/keys."
        )
        sys.exit(1)

    bar = "=" * 64

    graph = build_support_graph(api_key)

    # ----------------------------- Session 1
    print(f"\n{bar}\n  Session 1 - thread_id={SESSION_1_THREAD}\n{bar}")
    print(f"User:  {SESSION_1_MESSAGE}\n")
    s1_reply = await run_turn(graph, SESSION_1_THREAD, SESSION_1_MESSAGE, USER_ID)
    print(f"Agent: {s1_reply}\n")
    print("  -> Preferences extracted and stored in MemantoStore.")

    # ----------------------------- Session 2 (new thread)
    print(f"\n{bar}\n  Session 2 - thread_id={SESSION_2_THREAD}  (fresh thread)\n{bar}")
    print("  Checkpointer state for this thread_id is EMPTY.")
    print("  Anything the agent 'knows' below came from MemantoStore.\n")
    print(f"User:  {SESSION_2_MESSAGE}\n")
    s2_reply = await run_turn(graph, SESSION_2_THREAD, SESSION_2_MESSAGE, USER_ID)
    print(f"Agent: {s2_reply}\n")

    peanut_safe = "peanut" not in s2_reply.lower() or any(
        phrase in s2_reply.lower()
        for phrase in ("avoid peanut", "no peanut", "skip peanut", "peanut-free")
    )
    verdict = (
        "OK - agent honored peanut allergy across threads"
        if peanut_safe
        else "CHECK MANUALLY"
    )
    print(f"{bar}\n  Cross-session recall: {verdict}\n{bar}\n")


if __name__ == "__main__":
    asyncio.run(main())

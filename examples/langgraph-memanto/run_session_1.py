#!/usr/bin/env python3
"""
Session 1 -- User shares context with the support concierge.

Run this first. The LangGraph workflow will:
1. Recall prior memories (none yet on a fresh agent).
2. Respond conversationally.
3. Extract durable facts/preferences from the user's turn and write them
   to Memanto.

After this script exits the Python process is gone, but every fact the user
shared lives on in Memanto's vector store. Run ``run_session_2.py`` in a
fresh process to prove the agent recalls them.

Usage:
    python run_session_1.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from graph import assistant_reply, build_graph, initial_state
from memanto_memory import memanto_session

USER_ID = "demo-user-001"

SESSION_1_TURNS = [
    "Hi! Quick intro: I'm Priya, a senior data engineer at Vertex Robotics. "
    "We run our entire platform on AWS in us-west-2 and I'm the on-call "
    "lead for the data ingestion stack.",
    "Heads up for future tickets -- I always prefer reply emails over phone "
    "calls, and please send any urgent comms through Slack rather than SMS. "
    "Also, our team's procurement budget for new tooling is locked at $2k "
    "per quarter so anything above that needs CFO approval.",
    "One more thing: we're planning to migrate from Kinesis to MSK by end "
    "of Q3 next year, so any recommendations you give us going forward "
    "should bias toward Kafka-compatible tooling.",
]


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("\n" + "=" * 72)
    print("  Session 1 -- Capturing context into Memanto")
    print(f"  user_id: {USER_ID}")
    print("=" * 72 + "\n")

    with memanto_session() as memory:
        graph = build_graph(memory)
        total_stored = 0

        for i, user_text in enumerate(SESSION_1_TURNS, start=1):
            print(f"[Turn {i}] USER:\n  {user_text}\n")
            result = graph.invoke(initial_state(USER_ID, user_text))
            print(f"[Turn {i}] ASSISTANT:\n  {assistant_reply(result)}\n")
            stored = result.get("stored_ids", [])
            total_stored += len(stored)
            print(f"  -> stored {len(stored)} memory(ies) in Memanto\n")

        print("=" * 72)
        print(f"  Session 1 complete. Stored {total_stored} total memories.")
        print("  Run `python run_session_2.py` next to prove cross-session recall.")
        print("=" * 72 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

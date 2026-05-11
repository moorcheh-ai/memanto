#!/usr/bin/env python3
"""
Session 2 -- Fresh process, new LangGraph state. Memanto remembers.

Run this AFTER ``run_session_1.py`` finishes. The LangGraph state object is
brand new (zero messages carried over), so the only way the assistant can
answer the questions below is by pulling memories from Memanto.

This is the core "cross-session recall" demonstration the bounty asks for.

Usage:
    python run_session_2.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from graph import assistant_reply, build_graph, initial_state
from memanto_memory import memanto_session

USER_ID = "demo-user-001"

PROBE_QUESTIONS = [
    "Remind me -- which cloud region do we run our platform in?",
    "Should I page you on your phone or send a Slack message for an urgent "
    "P1 incident?",
    "We're evaluating a new streaming tool that costs $3,200/quarter. Any "
    "blockers given what you've told me before?",
    "Looking at the Q3 roadmap -- does our planned platform migration affect "
    "the tools I should be recommending?",
]


def _heuristic_recall_check(replies: list[str]) -> bool:
    """Lightweight smoke check that the answers reference stored memories."""
    blob = " ".join(replies).lower()
    expected_hits = ["us-west-2", "slack", "cfo", "kafka"]
    return sum(token in blob for token in expected_hits) >= 2


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("\n" + "=" * 72)
    print("  Session 2 -- Cross-session recall via Memanto")
    print(f"  user_id: {USER_ID}")
    print("  (Note: this is a fresh process; LangGraph state is empty.)")
    print("=" * 72 + "\n")

    with memanto_session() as memory:
        graph = build_graph(memory)
        replies: list[str] = []

        for i, question in enumerate(PROBE_QUESTIONS, start=1):
            print(f"[Probe {i}] USER:\n  {question}\n")
            result = graph.invoke(initial_state(USER_ID, question))
            reply = assistant_reply(result)
            replies.append(reply)
            recalled = result.get("recalled", [])
            print(f"[Probe {i}] ASSISTANT (recalled {len(recalled)} memories):\n  {reply}\n")

        recall_ok = _heuristic_recall_check(replies)
        print("=" * 72)
        print(
            "  Cross-session recall heuristic: "
            f"{'PASS' if recall_ok else 'FAIL -- review run_session_1 output'}"
        )
        print("=" * 72 + "\n")
        return 0 if recall_ok else 1


if __name__ == "__main__":
    sys.exit(main())

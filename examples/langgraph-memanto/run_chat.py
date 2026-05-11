#!/usr/bin/env python3
"""
Interactive REPL for the LangGraph + Memanto support concierge.

Useful for recording demo videos. Every user turn flows through:

    recall -> respond -> extract

so the agent learns about you on the fly and remembers across restarts.

Usage:
    python run_chat.py [--user-id <id>]
    (type 'exit' or Ctrl-C to quit)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from graph import assistant_reply, build_graph, initial_state
from memanto_memory import memanto_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default="demo-user-001")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("\n" + "=" * 72)
    print("  LangGraph + Memanto Support Concierge -- interactive REPL")
    print(f"  user_id: {args.user_id}")
    print("  (type 'exit' to quit)")
    print("=" * 72 + "\n")

    with memanto_session() as memory:
        graph = build_graph(memory)

        while True:
            try:
                user_text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            if user_text.lower() in {"exit", "quit", ":q"}:
                break

            result = graph.invoke(initial_state(args.user_id, user_text))
            print(f"\nassistant> {assistant_reply(result)}")
            stored = result.get("stored_ids", [])
            recalled = result.get("recalled", [])
            print(
                f"  (recalled {len(recalled)} memories, "
                f"stored {len(stored)} new memories)\n"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

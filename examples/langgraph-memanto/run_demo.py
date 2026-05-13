#!/usr/bin/env python3
"""Run the LangGraph + Memanto cross-session recall demo."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from dotenv import load_dotenv
from graph import build_support_graph
from memory_store import DEFAULT_AGENT_ID, build_memory_store
from state import SupportState

SESSION_ONE = (
    "I am Lina from Northstar Bikes. We run warranty returns in Europe, "
    "prefer concise technical answers, and our staging cluster is failing "
    "OAuth redirects after CDN changes."
)

SESSION_TWO = (
    "Can you remind me what Northstar Bikes cares about and what issue "
    "I should prioritize first?"
)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(argv)
    agent_id = args.agent_id or os.environ.get(
        "MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID
    )

    if args.mode == "full":
        _run_once(agent_id, args.live, args.reset, "yesterday", SESSION_ONE)
        print("\n--- new process / no LangGraph thread state carried over ---\n")
        _run_once(agent_id, args.live, False, "today", SESSION_TWO)
        return 0

    message = SESSION_ONE if args.mode == "seed" else SESSION_TWO
    session_label = "yesterday" if args.mode == "seed" else "today"
    _run_once(agent_id, args.live, args.reset, session_label, message)
    return 0


def _run_once(
    agent_id: str,
    live: bool,
    reset_preview: bool,
    session_label: str,
    message: str,
) -> None:
    store = build_memory_store(live=live, agent_id=agent_id, reset_preview=reset_preview)
    try:
        graph = build_support_graph(store)
        state: SupportState = {
            "customer_id": "northstar-bikes",
            "message": message,
            "session_label": session_label,
        }
        result = graph.invoke(state)
        _print_result(result, live=live)
    finally:
        store.close()


def _print_result(result: SupportState, live: bool) -> None:
    mode = "live Memanto" if live else "local preview"
    print(f"Mode: {mode}")
    print(f"Session: {result['session_label']}")
    print(f"Input: {result['message']}")
    print("\nRecalled memories:")
    memories = result.get("recalled_memories", [])
    if memories:
        for memory in memories:
            print(f"- [{memory['type']}] {memory['title']}: {memory['content']}")
    else:
        print("- none")

    print("\nAgent response:")
    print(result.get("response", ""))

    print("\nStored this run:")
    for memory in result.get("new_memories", []):
        print(f"- [{memory['type']}] {memory['title']}")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("seed", "recall", "full"),
        default="full",
        help="Run only the first session, only recall, or the complete proof.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live Memanto via MOORCHEH_API_KEY instead of local preview mode.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear local preview memories before the first run.",
    )
    parser.add_argument(
        "--agent-id",
        help="Memanto agent id / namespace. Defaults to MEMANTO_LANGGRAPH_AGENT_ID.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())

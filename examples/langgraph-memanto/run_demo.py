#!/usr/bin/env python3
"""Run the LangGraph + Memanto cross-session recall demo."""

from __future__ import annotations

import argparse
import os
import warnings
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from dotenv import load_dotenv
from memory_adapter import InMemoryMemantoStore, SdkMemantoStore

DEFAULT_AGENT_ID = "langgraph-memanto-support"
USER_ID = "customer-dana"


def main() -> None:
    args = _parse_args()
    load_dotenv()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from support_agent import run_support_turn

    mode = args.mode
    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if mode == "memanto" and not api_key:
        raise SystemExit("MOORCHEH_API_KEY is required for --mode memanto")

    store = (
        SdkMemantoStore(api_key=api_key, agent_id=args.agent_id)
        if mode == "memanto"
        else InMemoryMemantoStore()
    )

    try:
        print("LangGraph + Memanto cross-session recall")
        print(f"memory_mode={mode}")
        print()

        first_turn = run_support_turn(
            memory_store=store,
            user_id=USER_ID,
            thread_id="yesterday-onboarding-call",
            message=(
                "Remember that Dana wants invoices emailed every Friday with "
                "the purchase order in the subject"
            ),
        )
        _print_turn("Session 1: capture a preference", first_turn)

        second_turn = run_support_turn(
            memory_store=store,
            user_id=USER_ID,
            thread_id="today-new-ticket",
            message="In a fresh support thread, how should I send Dana's invoice?",
        )
        _print_turn("Session 2: answer from memory", second_turn)
    finally:
        close = getattr(store, "close", None)
        if close:
            with suppress(Exception):
                close()


def _print_turn(title: str, state: Mapping[str, Any]) -> None:
    print(title)
    print(f"thread_id={state['thread_id']}")
    print(f"user={state['user_id']}")
    print(f"user_message={state['message']}")
    print(f"recalled_memories={len(state.get('recalled_memories', []))}")
    if state.get("stored_memory_id"):
        print(f"stored_memory_id={state['stored_memory_id']}")
    print(f"agent_response={state['response']}")
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demonstrate LangGraph using Memanto as long-term memory.",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "memanto"),
        default="dry-run",
        help="Use dry-run for local smoke tests or memanto for the real SDK.",
    )
    parser.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ID,
        help="Memanto agent id to use in real SDK mode.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()

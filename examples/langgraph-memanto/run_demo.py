#!/usr/bin/env python3
"""Run the LangGraph + Memanto cross-session support demo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from memory_backend import LocalJsonMemory, MemantoMemory, MemoryBackend
from support_graph import SupportState, run_turn

USER_ID = "customer-priya"
SESSION_ONE_MESSAGE = (
    "My name is Priya. I need help with order PR-1842. "
    "Please remember that I prefer replacement before refund, and my launch is May 28."
)
SESSION_TWO_MESSAGE = (
    "This is a new chat. Do you remember my order and how I want the issue handled?"
)


def main() -> None:
    load_dotenv()
    args = parse_args()
    backend = build_backend(args)

    if args.backend == "local" and args.reset_local:
        assert isinstance(backend, LocalJsonMemory)
        backend.clear()

    if args.mode in {"session1", "full"}:
        print_header("Session 1: store durable support context")
        session_one = run_turn(
            backend=backend,
            session_id="day-one-langgraph-thread",
            user_id=USER_ID,
            user_message=SESSION_ONE_MESSAGE,
        )
        print_result(session_one)

    if args.mode in {"session2", "full"}:
        print_header("Session 2: fresh graph recalls yesterday's memory")
        session_two = run_turn(
            backend=backend,
            session_id="day-two-new-langgraph-thread",
            user_id=USER_ID,
            user_message=SESSION_TWO_MESSAGE,
        )
        print_result(session_two)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=("local", "memanto"),
        default="local",
        help="Use local JSON memory or the live Memanto SDK backend.",
    )
    parser.add_argument(
        "--mode",
        choices=("session1", "session2", "full"),
        default="full",
        help="Run one session or the complete two-session demo.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Clear the local JSON store before running.",
    )
    parser.add_argument(
        "--local-store",
        default=".memanto_langgraph_memory.json",
        help="Path used by the local JSON backend.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get(
            "MEMANTO_LANGGRAPH_AGENT_ID", "langgraph-support-memory-demo"
        ),
        help="Memanto agent id for the live backend.",
    )
    return parser.parse_args()


def build_backend(args: argparse.Namespace) -> MemoryBackend:
    if args.backend == "local":
        return LocalJsonMemory(Path(args.local_store))

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit(
            "MOORCHEH_API_KEY is required for --backend memanto. "
            "Copy .env.example to .env and add your key."
        )
    return MemantoMemory(api_key=api_key, agent_id=args.agent_id)


def print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def print_result(state: SupportState) -> None:
    print(f"Thread: {state['session_id']}")
    print(f"User:   {state['user_message']}")
    print("\nRecalled memories:")
    if state["recalled_memories"]:
        for memory in state["recalled_memories"]:
            print(f"- [{memory.memory_type}] {memory.content}")
    else:
        print("- none")

    print("\nAgent response:")
    print(state["response"])

    if state["stored_memories"]:
        print("\nStored memories:")
        for memory in state["stored_memories"]:
            print(f"- [{memory.memory_type}] {memory.content}")


if __name__ == "__main__":
    main()

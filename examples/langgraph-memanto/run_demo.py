#!/usr/bin/env python3
"""Run the LangGraph + Memanto cross-session memory demo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from memanto_langgraph import (
    LocalJsonMemantoStore,
    MemantoLangGraphStore,
    build_customer_success_graph,
)

LOCAL_MEMORY_PATH = Path(__file__).with_name(".local_memories.json")

SESSION_ONE = {
    "customer_id": "acme-health",
    "session_label": "day-one",
    "message": (
        "I'm Priya from Acme Health. Support ticket AR-8841 is blocked. "
        "We are under HIPAA, prefer concise bullet-point updates, and our "
        "account policy is replacement-before-refund."
    ),
}

SESSION_TWO = {
    "customer_id": "acme-health",
    "session_label": "day-two",
    "message": (
        "Brand new LangGraph thread for support ticket AR-8841. What durable "
        "customer constraints should I remember before answering?"
    ),
}


def main() -> None:
    args = parse_args()
    load_dotenv_if_available()

    if args.backend == "local" and args.reset_local and LOCAL_MEMORY_PATH.exists():
        LOCAL_MEMORY_PATH.unlink()

    store_one, cleanup_one = make_store(args)
    try:
        first = invoke_fresh_graph(store_one, SESSION_ONE)
    finally:
        cleanup_one()

    # Re-open the store and compile a new graph to prove the second run does
    # not depend on the first run's LangGraph state object.
    store_two, cleanup_two = make_store(args)
    try:
        second = invoke_fresh_graph(store_two, SESSION_TWO)
    finally:
        cleanup_two()

    print("\n=== Session 1: memory write ===")
    print(json.dumps(public_summary(first), indent=2))
    print("\n=== Session 2: fresh graph recalls Memanto memory ===")
    print(json.dumps(public_summary(second), indent=2))
    print("\nCross-session recall:")
    for memory in second["recalled_memories"]:
        print(f"- {memory}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=("local", "memanto"),
        default="local",
        help="Use local JSON persistence or live Memanto.",
    )
    parser.add_argument(
        "--agent-id",
        default="langgraph-memanto-customer-success",
        help="Memanto agent id for the live backend.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Moorcheh API key. Defaults to MOORCHEH_API_KEY.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Delete the local JSON memory file before running.",
    )
    return parser.parse_args()


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def make_store(args: argparse.Namespace):
    if args.backend == "local":
        return LocalJsonMemantoStore(LOCAL_MEMORY_PATH), lambda: None

    api_key = args.api_key or os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit("Set MOORCHEH_API_KEY or pass --api-key for live Memanto.")

    from memanto.cli.client.sdk_client import SdkClient

    client = SdkClient(api_key=api_key)
    try:
        client.create_agent(
            agent_id=args.agent_id,
            pattern="support",
            description="LangGraph customer success memory demo",
        )
    except Exception:
        pass
    client.activate_agent(args.agent_id, duration_hours=6)
    return MemantoLangGraphStore(client, args.agent_id), lambda: safe_deactivate(
        client,
        args.agent_id,
    )


def safe_deactivate(client: Any, agent_id: str) -> None:
    try:
        client.deactivate_agent(agent_id)
    except Exception:
        pass


def invoke_fresh_graph(store: Any, inputs: dict[str, str]) -> dict[str, Any]:
    graph = build_customer_success_graph(store)
    state = {
        **inputs,
        "recalled_memories": [],
        "response": "",
        "stored_memory_keys": [],
    }
    return graph.invoke(state)


def public_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": state["customer_id"],
        "session_label": state["session_label"],
        "recalled_count": len(state["recalled_memories"]),
        "stored_memory_keys": state["stored_memory_keys"],
        "response": state["response"],
    }


if __name__ == "__main__":
    main()

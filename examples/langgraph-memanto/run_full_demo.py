"""Run both LangGraph sessions in one process for local verification."""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from graph import build_support_graph, first_session_input, second_session_input
from memanto_memory import (
    InMemoryMemantoClient,
    create_sdk_client,
    dump_json,
    setup_memanto_session,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use an in-memory Memanto client so no API keys are required.",
    )
    args = parser.parse_args()

    load_dotenv()
    agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-customer-memory-demo")

    if args.dry_run:
        client = InMemoryMemantoClient()
    else:
        api_key = os.environ["MOORCHEH_API_KEY"]
        client = create_sdk_client(api_key)
        setup_memanto_session(client, agent_id=agent_id)

    graph = build_support_graph(client, agent_id=agent_id)

    print("=== Session 1: store memory outside LangGraph state ===")
    first_result = graph.invoke(first_session_input())
    print(dump_json(first_result))

    print("\n=== Session 2: recall with empty current graph state ===")
    second_result = graph.invoke(second_session_input())
    print(dump_json(second_result))


if __name__ == "__main__":
    main()

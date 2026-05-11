"""Session 1: store customer facts in Memanto through the LangGraph workflow."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from graph import build_support_graph, first_session_input
from memanto_memory import (
    InMemoryMemantoClient,
    create_sdk_client,
    dump_json,
    setup_memanto_session,
)


def main() -> None:
    load_dotenv()
    dry_run = os.getenv("MEMANTO_DRY_RUN") == "1"
    agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-customer-memory-demo")

    if dry_run:
        client = InMemoryMemantoClient()
    else:
        api_key = os.environ["MOORCHEH_API_KEY"]
        client = create_sdk_client(api_key)
        setup_memanto_session(client, agent_id=agent_id)

    graph = build_support_graph(client, agent_id=agent_id)
    result = graph.invoke(first_session_input())
    print(dump_json(result))


if __name__ == "__main__":
    main()

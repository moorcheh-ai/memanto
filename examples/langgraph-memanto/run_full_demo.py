from __future__ import annotations

import argparse
import os
from pathlib import Path

from memory_backends import create_memory_backend
from support_graph import build_support_graph, print_run_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full two-session LangGraph + Memanto memory demo."
    )
    parser.add_argument("--backend", default=os.environ.get("MEMANTO_LANGGRAPH_BACKEND", "local"))
    parser.add_argument("--agent-id", default=os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", "langgraph-support-demo"))
    parser.add_argument("--store", default=".langgraph_memanto_memory.json")
    parser.add_argument("--reset-local", action="store_true")
    args = parser.parse_args()

    if args.backend == "local" and args.reset_local:
        Path(args.store).unlink(missing_ok=True)

    backend = create_memory_backend(args.backend, args.store)
    graph = build_support_graph(backend)

    print("=== Run 1: support agent stores durable customer context ===")
    first = graph.invoke(
        {
            "agent_id": args.agent_id,
            "session_label": "session-1-store",
            "should_store": True,
        }
    )
    print_run_summary(first)

    print("\n=== Run 2: new support session recalls prior context ===")
    second = graph.invoke(
        {
            "agent_id": args.agent_id,
            "session_label": "session-2-recall",
            "should_store": False,
        }
    )
    print_run_summary(second)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import os

from memory_backends import create_memory_backend
from support_graph import build_support_graph, print_run_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run session 1: store customer memories through a LangGraph flow."
    )
    parser.add_argument("--backend", default=os.environ.get("MEMANTO_LANGGRAPH_BACKEND", "local"))
    parser.add_argument("--agent-id", default=os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", "langgraph-support-demo"))
    parser.add_argument("--store", default=".langgraph_memanto_memory.json")
    args = parser.parse_args()

    backend = create_memory_backend(args.backend, args.store)
    graph = build_support_graph(backend)
    result = graph.invoke(
        {
            "agent_id": args.agent_id,
            "session_label": "session-1-store",
            "should_store": True,
        }
    )
    print_run_summary(result)


if __name__ == "__main__":
    main()

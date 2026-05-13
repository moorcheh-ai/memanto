#!/usr/bin/env python3
"""Run the LangGraph + Memanto support example."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from langgraph_memanto import (
    DEFAULT_AGENT_ID,
    DEFAULT_CUSTOMER_ID,
    InMemoryMemoryStore,
    MemantoMemoryStore,
    build_graph,
)

SEED_MESSAGE = (
    "Yesterday Ada said invoice INV-1001 is blocking the Enterprise Pro "
    "renewal and she prefers concise replies."
)
RECALL_MESSAGE = (
    "Start a fresh support session for Ada. What prior invoice or renewal "
    "context should I use?"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["preview", "memanto"], default="preview")
    parser.add_argument("--phase", choices=["seed", "recall", "full"], default="full")
    parser.add_argument("--customer-id", default=DEFAULT_CUSTOMER_ID)
    parser.add_argument("--agent-id", default=os.getenv("MEMANTO_LANGGRAPH_AGENT_ID"))
    args = parser.parse_args()

    if args.backend == "preview" and args.phase != "full":
        parser.error("preview uses in-process memory; use --phase full")

    with memory_store(args.backend, args.agent_id) as memory:
        graph = build_graph(memory)

        if args.phase in {"seed", "full"}:
            run_phase(graph, customer_id=args.customer_id, label="seed")

        if args.phase in {"recall", "full"}:
            recall_result = run_phase(
                graph,
                customer_id=args.customer_id,
                label="recall",
            )
            if not recall_result.get("recalled_memories"):
                raise SystemExit("No memories were recalled; run seed first.")

    return 0


@contextmanager
def memory_store(backend: str, agent_id: str | None) -> Iterator[object]:
    if backend == "preview":
        yield InMemoryMemoryStore()
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit("MOORCHEH_API_KEY is required for --backend memanto")

    store = MemantoMemoryStore(
        api_key=api_key,
        agent_id=agent_id or DEFAULT_AGENT_ID,
    )
    try:
        yield store
    finally:
        store.close()


def run_phase(graph: object, *, customer_id: str, label: str) -> dict[str, object]:
    message = SEED_MESSAGE if label == "seed" else RECALL_MESSAGE
    result = graph.invoke({"customer_id": customer_id, "message": message})

    print(f"\n[{label}] customer_id={customer_id}")
    print(f"Input: {message}")
    print(f"Recalled memories: {len(result.get('recalled_memories', []))}")
    print(f"Response:\n{result.get('response')}")

    written = result.get("memory_to_write")
    if written:
        print(f"Stored memory: {written.get('title')} ({written.get('memory_id')})")

    return dict(result)


if __name__ == "__main__":
    sys.exit(main())

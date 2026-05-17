#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

from graph import build_support_graph
from memory_store import LocalJsonMemoryStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_path = Path(tmpdir) / "memories.json"
        first_graph = build_support_graph(LocalJsonMemoryStore(memory_path))
        first_graph.invoke(
            {
                "customer_id": "Maya",
                "thread_id": "session-one",
                "message": (
                    "I am Maya. My order is AR-8841, and I prefer replacement "
                    "units before refunds."
                ),
            }
        )

        second_graph = build_support_graph(LocalJsonMemoryStore(memory_path))
        result = second_graph.invoke(
            {
                "customer_id": "Maya",
                "thread_id": "session-two",
                "message": "What should you remember about my last order?",
            }
        )

        answer = result["answer"].lower()
        if "ar-8841" not in answer or "replacement" not in answer:
            raise SystemExit(f"offline validation failed: {result['answer']}")

    print("offline validation passed")


if __name__ == "__main__":
    main()

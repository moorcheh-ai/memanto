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
        first_result = first_graph.invoke(
            {
                "customer_id": "Maya",
                "thread_id": "session-one",
                "message": (
                    "I am Maya. My order is AR-8841, and I prefer replacement "
                    "units before refunds."
                ),
            }
        )

        if first_result["thread_id"] != "session-one":
            raise SystemExit("offline validation failed: session one thread mismatch")
        if not memory_path.exists():
            raise SystemExit("offline validation failed: memory file was not created")

        second_graph = build_support_graph(LocalJsonMemoryStore(memory_path))
        result = second_graph.invoke(
            {
                "customer_id": "Maya",
                "thread_id": "session-two",
                "message": "What should you remember about my last order?",
            }
        )

        if result["thread_id"] != "session-two":
            raise SystemExit("offline validation failed: session two thread mismatch")
        if not result.get("recalled_memories"):
            raise SystemExit("offline validation failed: no durable memories were recalled")

        answer = result["answer"].lower()
        if "ar-8841" not in answer or "replacement" not in answer:
            raise SystemExit(f"offline validation failed: {result['answer']}")

        print("offline validation passed")
        print("session-one stored durable order and preference memories")
        print("session-two used a fresh thread and recalled AR-8841 + replacement preference")


if __name__ == "__main__":
    main()

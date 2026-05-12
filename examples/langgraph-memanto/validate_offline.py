#!/usr/bin/env python3
"""No-secret validation for the LangGraph + Memanto example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from memanto_langgraph import LocalJsonMemantoStore, build_customer_success_graph
from run_demo import SESSION_ONE, SESSION_TWO


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        memory_path = Path(tmp) / "memories.json"

        session_one_store = LocalJsonMemantoStore(memory_path)
        first_graph = build_customer_success_graph(session_one_store)
        first = first_graph.invoke(
            {
                **SESSION_ONE,
                "recalled_memories": [],
                "response": "",
                "stored_memory_keys": [],
            }
        )

        assert first["stored_memory_keys"], "session one should store memories"

        # Fresh store object, fresh compiled graph, same persistent JSON file.
        session_two_store = LocalJsonMemantoStore(memory_path)
        second_graph = build_customer_success_graph(session_two_store)
        second = second_graph.invoke(
            {
                **SESSION_TWO,
                "recalled_memories": [],
                "response": "",
                "stored_memory_keys": [],
            }
        )

        recalled_text = "\n".join(second["recalled_memories"])
        expected = [
            "AR-8841",
            "HIPAA",
            "concise bullet-point updates",
            "replacement-before-refund",
        ]
        missing = [text for text in expected if text not in recalled_text]
        assert not missing, f"missing recalled memories: {missing}"

        namespace = ("customers", "acme-health", "memories")
        namespaces = session_two_store.list_namespaces(prefix=("customers",))
        assert namespace in namespaces

    print("offline validation passed")


if __name__ == "__main__":
    main()

"""Offline tests for the LangGraph + Memanto example."""

from __future__ import annotations

import sys
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from memory_store import InMemoryLongTermMemory  # noqa: E402
from support_graph import (  # noqa: E402
    build_support_graph,
    seed_yesterday,
)


def test_in_memory_recall_returns_cross_session_context() -> None:
    memory = InMemoryLongTermMemory()
    seed_yesterday(memory, user_id="maya")

    recalled = memory.recall(
        "maya receipt delayed order",
        memory_types=["preference", "fact"],
        limit=5,
    )

    assert len(recalled) == 2
    assert any("email" in item["content"] for item in recalled)
    assert any("A-1007" in item["content"] for item in recalled)


def test_langgraph_run_recalls_and_writes_long_term_memory() -> None:
    memory = InMemoryLongTermMemory()
    seed_yesterday(memory, user_id="maya")
    graph = build_support_graph(memory)

    result = graph.invoke(
        {
            "user_id": "maya",
            "message": "Can you send my receipt?",
            "session_label": "pytest-session",
        }
    )

    assert "retrieved_memories" in result
    assert len(result["retrieved_memories"]) == 2
    assert "email" in result["response"]
    assert result["stored_memory_id"] == "mem-3"
    assert len(memory.memories) == 3

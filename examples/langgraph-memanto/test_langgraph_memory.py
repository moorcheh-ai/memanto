"""Tests for the LangGraph + Memanto example.

Run from this directory after installing requirements:
    python -m pytest test_langgraph_memory.py
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from graph import build_memory_graph, extract_memories_from_message  # noqa: E402
from memory_store import InMemoryMemoryStore  # noqa: E402


def test_extracts_typed_memories_from_explicit_user_message() -> None:
    memories = extract_memories_from_message(
        "My name is Sam. I prefer bullet points. My project is a support bot.",
        user_id="demo-user",
    )

    assert {memory["type"] for memory in memories} == {"fact", "preference", "context"}
    assert any("Sam" in memory["content"] for memory in memories)
    assert any("bullet points" in memory["content"] for memory in memories)
    assert any("support bot" in memory["content"] for memory in memories)


def test_graph_stores_and_recalls_memory_across_graph_instances() -> None:
    store = InMemoryMemoryStore()

    first_graph = build_memory_graph(store)
    learn_result = first_graph.invoke(
        {
            "user_id": "demo-user",
            "message": (
                "My name is Sam. I prefer concise bullet points. "
                "My project is a LangGraph support bot."
            ),
        }
    )

    assert learn_result["stored_memory_ids"]
    assert len(store.memories) == 3

    second_graph = build_memory_graph(store)
    recall_result = second_graph.invoke(
        {
            "user_id": "demo-user",
            "message": "What do you remember about my preferences and project?",
        }
    )

    response = recall_result["response"]
    assert "I found these persisted memories" in response
    assert "concise bullet points" in response
    assert "LangGraph support bot" in response

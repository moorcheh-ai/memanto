from __future__ import annotations

from pathlib import Path

from graph import build_support_graph
from memory_store import LocalJsonMemoryStore


def test_local_store_persists_memories_across_instances(tmp_path: Path) -> None:
    memory_file = tmp_path / "memories.json"

    first_store = LocalJsonMemoryStore(memory_file)
    first_store.remember(
        memory_type="preference",
        title="Replacement preference",
        content="Maya prefers replacement units before refunds.",
        tags=["support", "maya"],
    )

    second_store = LocalJsonMemoryStore(memory_file)
    memories = second_store.recall("replacement refund preference", limit=3)

    assert len(memories) == 1
    assert memories[0]["title"] == "Replacement preference"
    assert "replacement units before refunds" in memories[0]["content"]


def test_graph_recalls_memanto_memory_without_thread_state(tmp_path: Path) -> None:
    memory_file = tmp_path / "support-memory.json"
    store = LocalJsonMemoryStore(memory_file)
    graph = build_support_graph(store)

    session_one = graph.invoke(
        {
            "customer_id": "maya",
            "message": (
                "I am Maya. My order is AR-8841, and I prefer replacement "
                "units before refunds."
            ),
            "thread_id": "session-one",
        }
    )

    fresh_store = LocalJsonMemoryStore(memory_file)
    fresh_graph = build_support_graph(fresh_store)
    session_two = fresh_graph.invoke(
        {
            "customer_id": "maya",
            "message": "What should you remember about my last order?",
            "thread_id": "session-two",
        }
    )

    assert session_one["thread_id"] == "session-one"
    assert session_two["thread_id"] == "session-two"
    assert session_two["recalled_memories"]
    assert "AR-8841" in session_two["answer"]
    assert "replacement" in session_two["answer"].lower()

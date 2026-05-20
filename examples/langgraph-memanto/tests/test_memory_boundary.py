from __future__ import annotations

from pathlib import Path

from graph import build_graph
from memory_store import LocalJsonMemoryStore
from run_demo import TODAY_MESSAGE, YESTERDAY_MESSAGE


def test_cross_session_recall_comes_from_memanto_not_graph_state(tmp_path: Path) -> None:
    store = LocalJsonMemoryStore(tmp_path / "memories.json")
    graph = build_graph(store)

    graph.invoke(
        {
            "agent_id": "test-agent",
            "session_id": "support-yesterday",
            "user_message": YESTERDAY_MESSAGE,
        }
    )
    today = graph.invoke(
        {
            "agent_id": "test-agent",
            "session_id": "support-today",
            "user_message": TODAY_MESSAGE,
        }
    )

    response = today["response"]
    assert "Northstar" in response
    assert "Friday" in response
    assert "May 28" in response
    assert all(
        memory["source_session"] == "support-yesterday"
        for memory in today["recalled_memories"]
    )


def test_fresh_agent_has_no_cross_session_memory(tmp_path: Path) -> None:
    store = LocalJsonMemoryStore(tmp_path / "memories.json")
    graph = build_graph(store)

    today = graph.invoke(
        {
            "agent_id": "empty-agent",
            "session_id": "support-today",
            "user_message": TODAY_MESSAGE,
        }
    )

    assert today["recalled_memories"] == []
    assert "do not have durable memory" in today["response"]

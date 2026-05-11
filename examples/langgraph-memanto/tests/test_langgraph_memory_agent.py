from __future__ import annotations

import pytest
from langgraph_memory_agent import JsonlMemantoStore, run_support_turn

pytest.importorskip("langgraph")


def test_langgraph_recalls_memanto_memory_across_sessions(tmp_path):
    memory_file = tmp_path / "memories.jsonl"

    first = run_support_turn(
        store=JsonlMemantoStore(memory_file),
        user_id="avery",
        question=(
            "Remember Avery wants dashboard walkthroughs in dark mode and "
            "reports exported as CSV."
        ),
        session_id="session-1",
    )

    second = run_support_turn(
        store=JsonlMemantoStore(memory_file),
        user_id="avery",
        question="How should I configure Avery's dashboard walkthrough?",
        session_id="session-2",
    )

    assert first["memory_written"] is not None
    assert first["memory_written"]["type"] == "preference"
    assert second["recalled_memories"]
    assert "dark mode" in second["response"]
    assert "CSV" in second["response"]


def test_local_memanto_store_filters_by_user_and_type(tmp_path):
    store = JsonlMemantoStore(tmp_path / "memories.jsonl")
    store.remember(
        user_id="avery",
        memory_type="preference",
        title="Avery theme",
        content="Avery prefers dark mode.",
        tags=["support"],
    )
    store.remember(
        user_id="blake",
        memory_type="preference",
        title="Blake theme",
        content="Blake prefers light mode.",
        tags=["support"],
    )
    store.remember(
        user_id="avery",
        memory_type="event",
        title="Avery call",
        content="Avery joined the kickoff call.",
        tags=["support"],
    )

    results = store.recall(
        user_id="avery",
        query="dashboard theme dark mode",
        memory_types=["preference"],
    )

    assert len(results) == 1
    assert results[0]["title"] == "Avery theme"

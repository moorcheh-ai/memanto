from __future__ import annotations

from pathlib import Path

import pytest
from langgraph_memanto_research_agent import (
    RESEARCHER_ID,
    TODAY_QUESTION,
    YESTERDAY_NOTES,
    LocalJsonMemory,
    extract_memories_to_store,
    make_recall_node,
    run_research_session,
)


def test_extracts_durable_preferences_from_yesterday() -> None:
    state = {
        "researcher_id": RESEARCHER_ID,
        "current_notes": [YESTERDAY_NOTES],
    }

    result = extract_memories_to_store(state)

    memory_types = {item.memory_type for item in result["memories_to_store"]}
    assert memory_types == {"preference", "instruction", "artifact"}


def test_local_backend_recalls_across_sessions_without_current_state(tmp_path: Path):
    pytest.importorskip("langgraph")

    backend = LocalJsonMemory(tmp_path / "memories.json")

    yesterday = run_research_session(
        backend,
        session_name="yesterday",
        researcher_id=RESEARCHER_ID,
        question="Capture durable preferences from the kickoff.",
        current_notes=[YESTERDAY_NOTES],
    )
    assert len(yesterday["stored_memories"]) == 3

    today = run_research_session(
        backend,
        session_name="today",
        researcher_id=RESEARCHER_ID,
        question=TODAY_QUESTION,
        current_notes=["No preferred format or source policy was restated today."],
    )

    current_state_text = " ".join(today["current_notes"]).lower()
    assert "atlasbench" not in current_state_text
    assert "vendor blog" not in current_state_text
    assert "benchmark table" not in current_state_text

    assert today["used_long_term_memory"] is True
    assert "compact benchmark table" in today["answer"]
    assert "avoid vendor blog posts" in today["answer"]
    assert "AtlasBench 2026" in today["answer"]


def test_recall_node_deduplicates_memories(tmp_path: Path) -> None:
    backend = LocalJsonMemory(tmp_path / "memories.json")
    state = {
        "researcher_id": RESEARCHER_ID,
        "current_notes": [YESTERDAY_NOTES],
    }
    for item in extract_memories_to_store(state)["memories_to_store"]:
        backend.remember(item)

    recall_node = make_recall_node(backend)
    result = recall_node(
        {
            "recall_queries": [
                f"{RESEARCHER_ID} vendor blogs",
                f"{RESEARCHER_ID} vendor blogs primary sources",
            ]
        }
    )

    ids = [item["memory_id"] for item in result["recalled_memories"]]
    assert len(ids) == len(set(ids))
    assert result["used_long_term_memory"] is True

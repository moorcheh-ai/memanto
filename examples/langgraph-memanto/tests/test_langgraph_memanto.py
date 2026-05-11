from __future__ import annotations

from pathlib import Path

from langgraph_memanto import (
    JsonMemoryStore,
    build_graph,
    extract_memories,
    run_turn,
)


def test_cross_session_recall_comes_from_memory_not_prompt(tmp_path: Path) -> None:
    memory = JsonMemoryStore(tmp_path / "memory.jsonl")
    graph = build_graph(memory)

    run_turn(
        graph=graph,
        session_id="intake-thread",
        user_message=(
            "I'm Maya from Nova Clinics. Please always escalate CSV export bugs "
            "to Priya. I prefer terse bullet replies. The launch review is Tuesday."
        ),
    )

    user_message = "CSV exports are failing again before launch. What matters?"
    result = run_turn(
        graph=graph,
        session_id="fresh-handoff-thread",
        user_message=user_message,
    )

    assert "Priya" not in user_message
    assert "terse bullet replies" not in user_message
    assert result["recalled_memories"]
    assert "Priya" in result["durable_answer"]
    assert "Priya" in result["answer"]
    assert "terse bullet replies" in result["answer"]
    assert "Tuesday" in result["answer"]


def test_extraction_creates_typed_atomic_memories() -> None:
    memories = extract_memories(
        "I'm Maya from Nova Clinics. Please always escalate CSV export bugs "
        "to Priya. I prefer terse bullet replies. The launch review is Tuesday."
    )

    by_type = {memory.type: memory for memory in memories}
    assert {"relationship", "instruction", "preference", "commitment"} <= set(by_type)
    assert by_type["relationship"].title == "Customer contact"
    assert by_type["instruction"].confidence == 0.86

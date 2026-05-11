import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from travel_concierge import (
    LocalJsonMemoryStore,
    extract_travel_memories,
    run_session,
)


def test_cross_session_recall_uses_memory_outside_fresh_graph_state(tmp_path: Path):
    store = LocalJsonMemoryStore(tmp_path / "memory.json")

    yesterday = run_session(
        store,
        message=(
            "I am Taku. I prefer vegetarian meals, need aisle seats, "
            "and I am traveling to Lisbon next Tuesday."
        ),
        session_label="yesterday",
    )
    assert yesterday["stored_memory_ids"]

    today = run_session(
        store,
        message="Please suggest a flight and hotel that fit my usual constraints.",
        session_label="today",
    )

    response = today["response"].lower()
    assert "vegetarian" in response
    assert "aisle" in response
    assert "lisbon" in response
    assert "usual constraints" in response
    assert "recalled" in response
    assert "recalled_memories" in today


def test_memory_extraction_stores_typed_atomic_travel_memories():
    memories = extract_travel_memories(
        "I prefer vegetarian meals and aisle seats when I fly to Lisbon next Tuesday.",
        session_id="yesterday",
    )

    memory_types = {memory.memory_type for memory in memories}
    titles = {memory.title for memory in memories}

    assert "preference" in memory_types
    assert "goal" in memory_types
    assert "context" in memory_types
    assert "Meal preference" in titles
    assert "Seat preference" in titles

"""Offline validation for the LangGraph + Memanto example.

This avoids repository-level pytest fixtures and does not require API keys.
"""

from __future__ import annotations

from memory_store import InMemoryLongTermMemory
from support_graph import draft_response, load_context, seed_yesterday, write_followup_memory


def main() -> None:
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

    state = {
        "user_id": "maya",
        "message": "Can you send my receipt?",
        "session_label": "offline-validation",
    }
    loaded = load_context(state, memory)
    drafted = draft_response(loaded)
    final = write_followup_memory(drafted, memory)

    assert "email" in drafted["response"]
    assert final["stored_memory_id"].startswith("mem-")
    assert len(memory.memories) == 3

    print("offline validation passed")


if __name__ == "__main__":
    main()

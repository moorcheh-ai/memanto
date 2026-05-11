"""Offline validation for the LangGraph + Memanto example."""

from __future__ import annotations

from pathlib import Path

from memory_backends import LocalJsonMemoryBackend
from support_agent import SupportAgent, run_support_turn


def main() -> int:
    path = Path(__file__).with_name(".validation-memory.json")
    backend = LocalJsonMemoryBackend(path)
    backend.reset()
    agent = SupportAgent(memory=backend)

    first = run_support_turn(
        agent=agent,
        thread_id="validation-thread-a",
        session_label="validation-day-1",
        customer_message=(
            "This is Priya from Northstar Dental. We prefer SMS updates. "
            "Our vendor is Kivo. Never include PHI and ask Dr. Rao for approval."
        ),
    )
    second = run_support_turn(
        agent=agent,
        thread_id="validation-thread-b",
        session_label="validation-day-2",
        customer_message="What do you remember from yesterday about our vendor update?",
    )

    assert first["persisted_memory_ids"], "session one should persist memories"
    assert second["thread_id"] != first["thread_id"], "threads must be isolated"
    assert len(second["recalled_memories"]) >= 3, "session two should recall memories"
    assert "Priya" in second["response"], "response should recall customer identity"
    assert "SMS" in second["response"], "response should recall channel preference"
    assert "PHI" in second["response"], "response should recall safety instruction"

    path.unlink(missing_ok=True)
    print("offline validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


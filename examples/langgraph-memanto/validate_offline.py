"""Offline validation for the LangGraph + Memanto example."""

from __future__ import annotations

from pathlib import Path

from memory_backends import LocalJsonMemoryBackend
from support_agent import SupportAgent, run_support_turn


def main() -> int:
    """Validate durable recall across isolated local graph threads."""
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

    if not first["persisted_memory_ids"]:
        raise SystemExit("session one should persist memories")
    if second["thread_id"] == first["thread_id"]:
        raise SystemExit("threads must be isolated")
    if len(second["recalled_memories"]) < 3:
        raise SystemExit("session two should recall memories")
    if "Priya" not in second["response"]:
        raise SystemExit("response should recall customer identity")
    if "SMS" not in second["response"]:
        raise SystemExit("response should recall channel preference")
    if "PHI" not in second["response"]:
        raise SystemExit("response should recall safety instruction")

    path.unlink(missing_ok=True)
    print("offline validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


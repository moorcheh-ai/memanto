"""Create a lived-in LlamaIndex Memory store through the public Memory API."""

from __future__ import annotations

import argparse
from pathlib import Path

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import Memory

SESSIONS = {
    "orchid-product": [
        (
            "user",
            "Our product is called Orchid. It helps small museums catalogue objects.",
            {"memory_type": "fact", "topic": "product"},
        ),
        (
            "assistant",
            "Understood: Orchid is a cataloguing product for small museums.",
            {"memory_type": "observation", "topic": "product"},
        ),
        (
            "user",
            "I prefer concise release notes with a short example before technical detail.",
            {"memory_type": "preference", "topic": "communication"},
        ),
        (
            "user",
            "We decided to ship offline-first sync before adding public sharing.",
            {"memory_type": "decision", "topic": "roadmap"},
        ),
        (
            "assistant",
            "I will keep public sharing out of the first launch plan.",
            {"memory_type": "commitment", "topic": "roadmap"},
        ),
        (
            "user",
            "The launch goal is to onboard 12 museums by October 15, 2026.",
            {"memory_type": "goal", "topic": "launch"},
        ),
        (
            "tool",
            "Created roadmap card ORC-42 for offline-first sync.",
            {
                "memory_type": "artifact",
                "topic": "roadmap",
                "tool_name": "roadmap.create_card",
                "tool_call_id": "call_orc_42",
                "result": {"card": "ORC-42", "status": "created"},
            },
        ),
        (
            "user",
            "Correction: the pilot museum count is 14, not 12; keep October 15.",
            {
                "memory_type": "fact",
                "topic": "launch",
                "supersedes": "pilot-count-12",
            },
        ),
    ],
    "orchid-research": [
        (
            "user",
            "Museum registrars need CSV import because many collections begin in spreadsheets.",
            {"memory_type": "observation", "topic": "research"},
        ),
        (
            "assistant",
            "That makes CSV import a launch-critical workflow, not an optional convenience.",
            {"memory_type": "learning", "topic": "research"},
        ),
        (
            "user",
            "Avoid collecting donor addresses; they are unnecessary for the catalogue.",
            {"memory_type": "instruction", "topic": "privacy"},
        ),
        (
            "user",
            "Mina is the registrar who will review the import template.",
            {"memory_type": "relationship", "topic": "pilot"},
        ),
        (
            "assistant",
            "The review with Mina is scheduled for September 3, 2026.",
            {"memory_type": "event", "topic": "pilot"},
        ),
    ],
}


def build_store(database: Path) -> int:
    """Populate ``database`` using LlamaIndex's real Memory persistence path."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite existing store: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    uri = f"sqlite+aiosqlite:///{database.resolve()}"
    count = 0
    for session_id, messages in SESSIONS.items():
        settings = {"session_id": session_id, "async_database_uri": uri}
        if session_id == "orchid-research":
            # A small queue exercises LlamaIndex's real active -> archived
            # waterfall while retaining every row in the persisted store.
            settings.update(
                token_limit=80,
                token_flush_size=20,
                chat_history_token_ratio=0.5,
            )
        memory = Memory.from_defaults(**settings)
        for role, content, metadata in messages:
            memory.put(
                ChatMessage(
                    role=role,
                    content=content,
                    additional_kwargs=metadata,
                )
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    count = build_store(args.database)
    print(f"Created {count} messages in {args.database}")


if __name__ == "__main__":
    main()

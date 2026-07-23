#!/usr/bin/env python3
"""
Deterministic sample ChatGPT data export generator.

Builds ``sample_data/chatgpt-export-sample/`` — a synthetic but
schema-faithful ChatGPT data export for demoing and testing the adapter
without anyone's real conversations. The shapes mirror a genuine export:

- ``conversations.json``: array of conversations with ``mapping`` node
  graphs, assistant->``bio`` memory writes, tool acknowledgements
  ("Model set context updated."), a ``model_editable_context`` snapshot
  replaying the accumulated memory list, and custom-instruction
  ``user_context_message_data`` metadata repeated across conversations.
- ``user.json``: placeholder account stub (the adapter never ingests it).

The story is a lived-in account: eight months of a firmware engineer's
assistant learning preferences, goals, relationships — including a
correction (moved cities) and a changed preference (coffee order), so the
migrated memory demonstrably carries *evolution*, not just facts.

Run from this directory:

    python3 make_sample_export.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).parent / "sample_data" / "chatgpt-export-sample"


def _ts(iso: str) -> float:
    """ISO date string -> unix timestamp (UTC), like real exports use."""
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


_CUSTOM_INSTRUCTIONS = {
    "about_user_message": (
        "I'm a firmware engineer. I work mostly in C and Rust on embedded "
        "sensor platforms. Keep examples small and hardware-realistic."
    ),
    "about_model_message": (
        "Be concise. Prefer code over prose. Flag unsafe memory patterns."
    ),
}


def _msg(
    msg_id: str,
    role: str,
    text: str,
    created: str,
    *,
    recipient: str = "all",
    name: str | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "id": msg_id,
        "author": {"role": role, "name": name, "metadata": {}},
        "create_time": _ts(created),
        "update_time": None,
        "content": {"content_type": "text", "parts": [text]},
        "status": "finished_successfully",
        "end_turn": True,
        "weight": 1.0,
        "metadata": metadata or {},
        "recipient": recipient,
    }


def _snapshot_msg(msg_id: str, snapshot: str, created: str) -> dict:
    return {
        "id": msg_id,
        "author": {"role": "system", "name": None, "metadata": {}},
        "create_time": _ts(created),
        "update_time": None,
        "content": {
            "content_type": "model_editable_context",
            "model_set_context": snapshot,
            "repository": None,
            "repo_summary": None,
        },
        "status": "finished_successfully",
        "end_turn": None,
        "weight": 1.0,
        "metadata": {},
        "recipient": "all",
    }


def _conversation(conv_id: str, title: str, created: str, messages: list[dict]) -> dict:
    mapping: dict[str, dict] = {
        "root": {"id": "root", "message": None, "parent": None, "children": []}
    }
    parent = "root"
    for message in messages:
        node_id = f"node-{message['id']}"
        mapping[parent]["children"].append(node_id)
        mapping[node_id] = {
            "id": node_id,
            "message": message,
            "parent": parent,
            "children": [],
        }
        parent = node_id
    return {
        "id": conv_id,
        "conversation_id": conv_id,
        "title": title,
        "create_time": _ts(created),
        "update_time": _ts(created),
        "mapping": mapping,
        "moderation_results": [],
        "current_node": parent,
    }


def build_conversations() -> list[dict]:
    """Eight months of a lived-in account, in ten conversations."""
    conversations = []

    # --- 2025-11: first contact — profile facts land in the bio tool.
    conversations.append(
        _conversation(
            "conv-001",
            "Debugging an I2C driver",
            "2025-11-04T09:12:00",
            [
                _msg(
                    "m-001a",
                    "system",
                    "",
                    "2025-11-04T09:12:00",
                    metadata={
                        "is_user_system_message": True,
                        "user_context_message_data": _CUSTOM_INSTRUCTIONS,
                    },
                ),
                _msg(
                    "m-001b",
                    "user",
                    "My I2C driver hangs on the second read. I'm a firmware "
                    "engineer at Meridian Robotics, mostly C on STM32.",
                    "2025-11-04T09:12:30",
                ),
                _msg(
                    "m-001c",
                    "assistant",
                    "User is a firmware engineer at Meridian Robotics working "
                    "on STM32 microcontrollers, primarily in C.",
                    "2025-11-04T09:12:45",
                    recipient="bio",
                ),
                _msg(
                    "m-001d",
                    "tool",
                    "Model set context updated.",
                    "2025-11-04T09:12:46",
                    name="bio",
                ),
                _msg(
                    "m-001e",
                    "assistant",
                    "A hang on the second read usually means the bus wasn't "
                    "released — check for a missing STOP condition.",
                    "2025-11-04T09:13:00",
                ),
            ],
        )
    )

    # --- 2025-11: preferences.
    conversations.append(
        _conversation(
            "conv-002",
            "Coffee brewing ratios",
            "2025-11-18T07:45:00",
            [
                _msg(
                    "m-002a",
                    "user",
                    "What ratio for a dark roast pour-over? That's my usual.",
                    "2025-11-18T07:45:00",
                ),
                _msg(
                    "m-002b",
                    "assistant",
                    "User prefers dark roast coffee, usually brewed as pour-over.",
                    "2025-11-18T07:45:20",
                    recipient="bio",
                ),
                _msg(
                    "m-002c",
                    "tool",
                    "Model set context updated.",
                    "2025-11-18T07:45:21",
                    name="bio",
                ),
                _msg(
                    "m-002d",
                    "assistant",
                    "Start at 1:15 and adjust toward 1:16 if it tastes muddy.",
                    "2025-11-18T07:46:00",
                ),
            ],
        )
    )

    # --- 2025-12: relationships.
    conversations.append(
        _conversation(
            "conv-003",
            "Gift ideas",
            "2025-12-09T19:30:00",
            [
                _msg(
                    "m-003a",
                    "user",
                    "Need a gift for my partner Sam. Our dog Biscuit chews "
                    "everything, so nothing fragile.",
                    "2025-12-09T19:30:00",
                ),
                _msg(
                    "m-003b",
                    "assistant",
                    "User's partner is named Sam. They have a dog named "
                    "Biscuit who chews on things.",
                    "2025-12-09T19:30:25",
                    recipient="bio",
                ),
                _msg(
                    "m-003c",
                    "tool",
                    "Model set context updated.",
                    "2025-12-09T19:30:26",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-01: goals.
    conversations.append(
        _conversation(
            "conv-004",
            "Marathon training plan",
            "2026-01-12T06:20:00",
            [
                _msg(
                    "m-004a",
                    "user",
                    "I signed up for the Chicago Marathon in October. Build "
                    "me a base plan — I run about 25 km a week now.",
                    "2026-01-12T06:20:00",
                ),
                _msg(
                    "m-004b",
                    "assistant",
                    "User is training for the Chicago Marathon in October "
                    "2026, currently running about 25 km per week.",
                    "2026-01-12T06:20:30",
                    recipient="bio",
                ),
                _msg(
                    "m-004c",
                    "tool",
                    "Model set context updated.",
                    "2026-01-12T06:20:31",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-02: a decision (language switch).
    conversations.append(
        _conversation(
            "conv-005",
            "Porting a driver to Rust",
            "2026-02-03T14:05:00",
            [
                _msg(
                    "m-005a",
                    "user",
                    "We decided to port our sensor drivers from C to Rust. "
                    "Where do I start with embedded-hal?",
                    "2026-02-03T14:05:00",
                ),
                _msg(
                    "m-005b",
                    "assistant",
                    "User's team decided to port their sensor drivers from C "
                    "to Rust using embedded-hal.",
                    "2026-02-03T14:05:30",
                    recipient="bio",
                ),
                _msg(
                    "m-005c",
                    "tool",
                    "Model set context updated.",
                    "2026-02-03T14:05:31",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-03: a correction — user moved cities. Shows memory evolving
    # with life changes, not just accumulating.
    conversations.append(
        _conversation(
            "conv-006",
            "Neighborhood advice",
            "2026-03-21T17:40:00",
            [
                _msg(
                    "m-006a",
                    "user",
                    "Update: we finally moved from Austin to Seattle last "
                    "week. Which neighborhoods are good for runners?",
                    "2026-03-21T17:40:00",
                ),
                _msg(
                    "m-006b",
                    "assistant",
                    "User moved to Seattle in March 2026, previously lived in Austin.",
                    "2026-03-21T17:40:30",
                    recipient="bio",
                ),
                _msg(
                    "m-006c",
                    "tool",
                    "Model set context updated.",
                    "2026-03-21T17:40:31",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-04: changed preference — corrects conv-002.
    conversations.append(
        _conversation(
            "conv-007",
            "Espresso machine shopping",
            "2026-04-08T08:10:00",
            [
                _msg(
                    "m-007a",
                    "user",
                    "I've gone off pour-over honestly — it's espresso now. "
                    "Recommend a machine under $600.",
                    "2026-04-08T08:10:00",
                ),
                _msg(
                    "m-007b",
                    "assistant",
                    "User now prefers espresso over pour-over coffee and is "
                    "shopping for an espresso machine under $600.",
                    "2026-04-08T08:10:30",
                    recipient="bio",
                ),
                _msg(
                    "m-007c",
                    "tool",
                    "Model set context updated.",
                    "2026-04-08T08:10:31",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-05: commitment.
    conversations.append(
        _conversation(
            "conv-008",
            "Conference talk outline",
            "2026-05-14T11:00:00",
            [
                _msg(
                    "m-008a",
                    "user",
                    "My embedded Rust talk got accepted for RustConf. Slides "
                    "are due August 15. Help me outline it.",
                    "2026-05-14T11:00:00",
                ),
                _msg(
                    "m-008b",
                    "assistant",
                    "User will speak about embedded Rust at RustConf; their "
                    "slides are due August 15, 2026.",
                    "2026-05-14T11:00:30",
                    recipient="bio",
                ),
                _msg(
                    "m-008c",
                    "tool",
                    "Model set context updated.",
                    "2026-05-14T11:00:31",
                    name="bio",
                ),
            ],
        )
    )

    # --- 2026-06: a conversation carrying the replayed memory snapshot,
    # plus one new bio write. The snapshot repeats earlier entries (dedup
    # exercise) and contributes two entries never seen as bio writes.
    snapshot = "\n".join(
        [
            "1. [2025-11-04]. User is a firmware engineer at Meridian "
            "Robotics working on STM32 microcontrollers, primarily in C.",
            "2. [2025-12-09]. User's partner is named Sam. They have a dog "
            "named Biscuit who chews on things.",
            "3. [2026-01-12]. User is training for the Chicago Marathon in "
            "October 2026, currently running about 25 km per week.",
            "4. [2026-02-14]. User is allergic to shellfish.",
            "5. [2026-04-08]. User now prefers espresso over pour-over "
            "coffee and is shopping for an espresso machine under $600.",
            "6. User keeps a sourdough starter named Clint Yeastwood.",
        ]
    )
    conversations.append(
        _conversation(
            "conv-009",
            "Meal prep for race week",
            "2026-06-02T18:25:00",
            [
                _msg(
                    "m-009a",
                    "system",
                    "",
                    "2026-06-02T18:25:00",
                    metadata={
                        "is_user_system_message": True,
                        "user_context_message_data": _CUSTOM_INSTRUCTIONS,
                    },
                ),
                _snapshot_msg("m-009b", snapshot, "2026-06-02T18:25:01"),
                _msg(
                    "m-009c",
                    "user",
                    "Plan carb-heavy dinners for race week. Remember no "
                    "shellfish. Sam eats vegetarian on weekdays.",
                    "2026-06-02T18:25:30",
                ),
                _msg(
                    "m-009d",
                    "assistant",
                    "User's partner Sam eats vegetarian on weekdays.",
                    "2026-06-02T18:26:00",
                    recipient="bio",
                ),
                _msg(
                    "m-009e",
                    "tool",
                    "Model set context updated.",
                    "2026-06-02T18:26:01",
                    name="bio",
                ),
            ],
        )
    )

    # --- Noise: a conversation with no memory activity at all.
    conversations.append(
        _conversation(
            "conv-010",
            "Regex help",
            "2026-06-20T15:00:00",
            [
                _msg(
                    "m-010a",
                    "user",
                    "Why does my lookbehind fail in JavaScript?",
                    "2026-06-20T15:00:00",
                ),
                _msg(
                    "m-010b",
                    "assistant",
                    "Older engines lack lookbehind support — check the "
                    "target runtime version.",
                    "2026-06-20T15:00:20",
                ),
            ],
        )
    )

    return conversations


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conversations = build_conversations()
    (OUT_DIR / "conversations.json").write_text(
        json.dumps(conversations, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Placeholder account stub — present for schema realism only. The
    # adapter never reads it, so no PII shape is exercised.
    (OUT_DIR / "user.json").write_text(
        json.dumps(
            {
                "id": "user-sample",
                "email": "sample@example.com",
                "chatgpt_plus_user": True,
                "phone_number": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Sample export written to {OUT_DIR}")
    print(f"  conversations: {len(conversations)}")


if __name__ == "__main__":
    main()

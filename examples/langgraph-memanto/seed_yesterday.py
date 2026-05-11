#!/usr/bin/env python3
from __future__ import annotations

from dotenv import load_dotenv
from memanto_memory import create_memory_from_env

YESTERDAY_MEMORIES = [
    {
        "content": (
            "maya-rivera is a Pro-tier customer using the solar monitoring "
            "dashboard for a rooftop inverter fleet."
        ),
        "memory_type": "fact",
        "tags": ["customer", "account", "support"],
    },
    {
        "content": (
            "maya-rivera prefers concise support updates with a short checklist "
            "and no long narrative."
        ),
        "memory_type": "preference",
        "tags": ["communication", "support"],
    },
    {
        "content": (
            "maya-rivera prefers email updates and does not want SMS follow-ups "
            "for this support case."
        ),
        "memory_type": "preference",
        "tags": ["communication", "email"],
    },
    {
        "content": (
            "maya-rivera is in the America/Los_Angeles timezone and asked for "
            "updates before 4 PM local time."
        ),
        "memory_type": "fact",
        "tags": ["timezone", "scheduling"],
    },
    {
        "content": (
            "Support issue INV-4832: maya-rivera reported that one inverter "
            "stopped sending telemetry after a firmware update."
        ),
        "memory_type": "event",
        "tags": ["support-case", "inverter", "telemetry"],
    },
    {
        "content": (
            "Decision for INV-4832: first check firmware rollback notes, then "
            "ask for the gateway diagnostic export only if telemetry is still stale."
        ),
        "memory_type": "decision",
        "tags": ["support-case", "next-step"],
    },
]


def seed_yesterday() -> None:
    load_dotenv()
    memory = create_memory_from_env()

    print("Writing yesterday's support memories into Memanto...\n")
    for item in YESTERDAY_MEMORIES:
        memory.remember(
            item["content"],
            memory_type=item["memory_type"],
            tags=item["tags"],
            confidence=0.92,
            provenance="explicit_statement",
        )
        print(f"- {item['memory_type']}: {item['content']}")

    print("\nDone. Close this process and run: python run_today.py")


def main() -> None:
    seed_yesterday()


if __name__ == "__main__":
    main()

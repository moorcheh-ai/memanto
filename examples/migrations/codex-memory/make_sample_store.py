#!/usr/bin/env python3
"""
make_sample_store.py — build a small, synthetic Codex store for testing.

The adapter's real target is a private store (`~/.codex`). To let anyone
reproduce the migration end to end without touching personal data, this script
writes a miniature store with the *same schema* the adapter reads:

    sample-codex-store/
      memories_1.sqlite    stage1_outputs
      goals_1.sqlite       thread_goals
      state_5.sqlite       threads
      sessions/2026/01/01/rollout-*.jsonl

Every value is invented. The point is schema fidelity, not content: if the
adapter runs against this store it will run against yours.

Usage
-----
    python make_sample_store.py --out ./sample-codex-store
    python codex_to_okf.py --codex-home ./sample-codex-store --out ./sample-bundle
    memanto migrate okf ./sample-bundle --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

THREADS = [
    ("019f0001-0000-7000-8000-000000000001", "weekend-trip-planner",
     "Plan a 3-day trip to Kyoto", "2026-01-02T09:00:00Z"),
    ("019f0001-0000-7000-8000-000000000002", "release-checklist",
     "Automate the release checklist", "2026-01-03T14:30:00Z"),
]

DISTILLED = [
    (
        THREADS[0][0],
        "The user prefers trains over flights for trips under 4 hours, always "
        "books accommodation within walking distance of a station, and dislikes "
        "itineraries with more than two activities per day.",
        "Planned a Kyoto itinerary; user corrected an over-packed schedule twice.",
        "kyoto-trip-planning",
    ),
    (
        THREADS[1][0],
        "Release automation must run the migration dry-run before applying it, "
        "and every step must be reversible with a recorded rollback command.",
        "Built a release checklist script; user rejected a non-reversible step.",
        "release-checklist-automation",
    ),
]

GOALS = [
    (THREADS[0][0], "goal-kyoto", "Produce a final 3-day Kyoto itinerary the user approves.", "active"),
    (THREADS[1][0], "goal-release", "Ship a one-command release pipeline with rollback.", "active"),
]


def _rollout_lines(thread_id: str) -> list[dict]:
    """A rollout transcript with the real Codex event shapes."""
    return [
        {
            "timestamp": "2026-01-02T09:00:01Z",
            "type": "session_meta",
            "payload": {
                "session_id": thread_id,
                "cwd": "~/work/trip",
                "originator": "codex_cli",
                "cli_version": "0.0.0-sample",
                "model_provider": "openai",
                "base_instructions": (
                    "You are a coding agent. Prefer reversible operations. "
                    "Never run a destructive command without showing a dry run first."
                ),
            },
        },
        {
            "timestamp": "2026-01-02T09:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Plan a 3-day Kyoto trip. I prefer trains."}],
            },
        },
        {
            "timestamp": "2026-01-02T09:00:12Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "The user stated a transport preference, so I should record it as a durable preference rather than a one-off constraint."}
                ],
            },
        },
        {
            "timestamp": "2026-01-02T09:00:18Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "search_trains",
                "arguments": json.dumps({"from": "Tokyo", "to": "Kyoto", "date": "2026-02-14"}),
            },
        },
        {
            "timestamp": "2026-01-02T09:00:24Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Drafted a 3-day plan built around the Shinkansen, with two activities per day."}],
            },
        },
        {
            "timestamp": "2026-01-02T09:40:00Z",
            "type": "compacted",
            "payload": {
                "summary": "Earlier back-and-forth about breakfast options was dropped; the transport preference and the two-activities-per-day rule were kept.",
                "replaced_turns": 12,
            },
        },
    ]


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)

    # --- memories_1.sqlite -------------------------------------------------
    con = sqlite3.connect(out / "memories_1.sqlite")
    con.execute(
        """
        CREATE TABLE stage1_outputs (
            thread_id TEXT PRIMARY KEY,
            source_updated_at INTEGER NOT NULL,
            raw_memory TEXT NOT NULL,
            rollout_summary TEXT NOT NULL,
            rollout_slug TEXT,
            generated_at INTEGER NOT NULL,
            usage_count INTEGER,
            last_usage INTEGER,
            selected_for_phase2 INTEGER NOT NULL DEFAULT 0,
            selected_for_phase2_source_updated_at INTEGER
        )
        """
    )
    for index, (thread_id, raw, summary, slug) in enumerate(DISTILLED):
        con.execute(
            "insert into stage1_outputs values (?,?,?,?,?,?,?,?,?,?)",
            (thread_id, 1767000000 + index, raw, summary, slug,
             1767000000 + index, 3, 1767001000, 0, None),
        )
    con.commit()
    con.close()

    # --- goals_1.sqlite ----------------------------------------------------
    con = sqlite3.connect(out / "goals_1.sqlite")
    con.execute(
        """
        CREATE TABLE thread_goals (
            thread_id TEXT PRIMARY KEY NOT NULL,
            goal_id TEXT NOT NULL,
            objective TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    con.executemany("insert into thread_goals values (?,?,?,?)", GOALS)
    con.commit()
    con.close()

    # --- state_5.sqlite ----------------------------------------------------
    con = sqlite3.connect(out / "state_5.sqlite")
    con.execute(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            title TEXT,
            cwd TEXT,
            created_at TEXT,
            updated_at TEXT,
            model TEXT,
            model_provider TEXT,
            status TEXT
        )
        """
    )
    for thread_id, slug, title, created in THREADS:
        con.execute(
            "insert into threads values (?,?,?,?,?,?,?,?)",
            (thread_id, title, "~/work/" + slug, created, created,
             "gpt-5-codex", "openai", "idle"),
        )
    con.commit()
    con.close()

    # --- sessions/**/rollout-*.jsonl --------------------------------------
    day = out / "sessions" / "2026" / "01" / "02"
    day.mkdir(parents=True, exist_ok=True)
    written = 0
    for thread_id, _slug, _title, created in THREADS:
        stamp = created.replace(":", "-").replace("Z", "")
        path = day / f"rollout-{stamp}-{thread_id}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for line in _rollout_lines(thread_id):
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        written += 1

    return {
        "store": str(out),
        "distilled_memories": len(DISTILLED),
        "goals": len(GOALS),
        "threads": len(THREADS),
        "rollouts": written,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a synthetic Codex store for testing.")
    parser.add_argument("--out", default="./sample-codex-store", help="Destination directory.")
    args = parser.parse_args(argv)

    result = build(Path(args.out).expanduser().resolve())
    print(f"Sample Codex store : {result['store']}")
    print(f"  distilled memories : {result['distilled_memories']}")
    print(f"  goals              : {result['goals']}")
    print(f"  threads            : {result['threads']}")
    print(f"  rollout transcripts: {result['rollouts']}")
    print("\nNow run:")
    print(f"  python codex_to_okf.py --codex-home {args.out} --out ./sample-bundle")
    print("  memanto migrate okf ./sample-bundle --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
      sessions/2026/01/02/rollout-*.jsonl
      sessions/2026/01/03/rollout-*.jsonl

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
import sys
from pathlib import Path

THREADS = [
    ("019f0001-0000-7000-8000-000000000001", "weekend-trip-planner",
     "Plan a 3-day trip to Kyoto", "2026-01-02T09:00:00Z"),
    ("019f0001-0000-7000-8000-000000000002", "release-checklist",
     "Automate the release checklist", "2026-01-03T14:30:00Z"),
]

# One scenario per thread. Each thread gets its own day, directory, request,
# reasoning, tool call, answer and compaction event, so the generated store
# exercises extraction for both sessions instead of repeating one transcript.
SCENARIOS: dict[str, dict] = {
    THREADS[0][0]: {
        "day": ("2026", "01", "02"),
        "date": "2026-01-02",
        "start": "09:00",
        "cwd": "~/work/trip",
        "base_instructions": (
            "You are a coding agent. Prefer reversible operations. "
            "Never run a destructive command without showing a dry run first."
        ),
        "user": "Plan a 3-day Kyoto trip. I prefer trains.",
        "reasoning": (
            "The user stated a transport preference, so I should record it as a "
            "durable preference rather than a one-off constraint."
        ),
        "tool": ("search_trains", {"from": "Tokyo", "to": "Kyoto", "date": "2026-02-14"}),
        "assistant": (
            "Drafted a 3-day plan built around the Shinkansen, "
            "with two activities per day."
        ),
        "compaction_summary": (
            "Earlier back-and-forth about breakfast options was dropped; "
            "the transport preference and the two-activities-per-day rule were kept."
        ),
        "compaction_turns": 12,
    },
    THREADS[1][0]: {
        "day": ("2026", "01", "03"),
        "date": "2026-01-03",
        "start": "14:30",
        "cwd": "~/work/release",
        "base_instructions": (
            "You are a coding agent. Prefer reversible operations. "
            "Never run a destructive command without showing a dry run first."
        ),
        "user": "Automate our release checklist. Every step must be reversible.",
        "reasoning": (
            "The user demanded reversibility, so each step has to emit its rollback "
            "command before it is applied, not after."
        ),
        "tool": ("run_release_step", {"step": "migrate-dry-run", "apply": False}),
        "assistant": (
            "Built a one-command release pipeline where every step prints its "
            "rollback command before it executes."
        ),
        "compaction_summary": (
            "The earlier comparison of three CI providers was dropped; "
            "reversibility and the dry-run rule were kept."
        ),
        "compaction_turns": 8,
    },
}

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


def _ts(date: str, clock: str, seconds: int) -> str:
    """`2026-01-03` + `14:30` + 5s -> `2026-01-03T14:30:05Z`."""
    hour, minute = (int(part) for part in clock.split(":"))
    minute += seconds // 60
    second = seconds % 60
    hour += minute // 60
    minute %= 60
    return f"{date}T{hour:02d}:{minute:02d}:{second:02d}Z"


def _rollout_lines(thread_id: str) -> list[dict]:
    """A rollout transcript with the real Codex event shapes."""
    scenario = SCENARIOS[thread_id]
    date = scenario["date"]
    clock = scenario["start"]
    tool_name, tool_args = scenario["tool"]
    return [
        {
            "timestamp": _ts(date, clock, 1),
            "type": "session_meta",
            "payload": {
                "session_id": thread_id,
                "cwd": scenario["cwd"],
                "originator": "codex_cli",
                "cli_version": "0.0.0-sample",
                "model_provider": "openai",
                "base_instructions": scenario["base_instructions"],
            },
        },
        {
            "timestamp": _ts(date, clock, 5),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": scenario["user"]}],
            },
        },
        {
            "timestamp": _ts(date, clock, 12),
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": scenario["reasoning"]}],
            },
        },
        {
            "timestamp": _ts(date, clock, 18),
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": tool_name,
                "arguments": json.dumps(tool_args),
            },
        },
        {
            "timestamp": _ts(date, clock, 24),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": scenario["assistant"]}],
            },
        },
        {
            "timestamp": _ts(date, clock, 40),
            "type": "compacted",
            "payload": {
                "summary": scenario["compaction_summary"],
                "replaced_turns": scenario["compaction_turns"],
            },
        },
    ]


class StoreExists(Exception):
    """Raised when the destination already holds a store and --force is off."""


def build(out: Path, *, force: bool = False) -> dict:
    if out.exists() and any(out.iterdir()) and not force:
        raise StoreExists(
            f"{out} is not empty. Building here would fail on the existing tables "
            f"(CREATE TABLE on a populated store raises). Pass --force to replace "
            f"it, or choose an empty --out path."
        )
    if force and out.exists():
        import shutil
        shutil.rmtree(out)
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
    for thread_id, _slug, title, created in THREADS:
        con.execute(
            "insert into threads values (?,?,?,?,?,?,?,?)",
            (thread_id, title, SCENARIOS[thread_id]["cwd"], created, created,
             "gpt-5-codex", "openai", "idle"),
        )
    con.commit()
    con.close()

    # --- sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl -------------------------
    written = 0
    for thread_id, _slug, _title, created in THREADS:
        # Each thread's transcript lives under its own date directory.
        day = out / "sessions" / Path(*SCENARIOS[thread_id]["day"])
        day.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--force", action="store_true",
                        help="Replace a non-empty destination directory.")
    args = parser.parse_args(argv)

    try:
        result = build(Path(args.out).expanduser().resolve(), force=args.force)
    except StoreExists as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

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

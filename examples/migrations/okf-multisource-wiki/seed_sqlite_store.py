"""Populate a proprietary SQLite agent-memory store (second lock-in source).

Many DIY agents keep facts in ad-hoc SQLite tables with their own schema.
This seeder creates that store via a real SQLite connection and inserts rows
across overlapping sessions so consolidation has conflicts to resolve.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    thread_id TEXT,
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    meta_json TEXT
);
"""

# Overlaps Chroma on name/timezone; disagrees on language preference (stale);
# adds unique operational facts Chroma never saw.
_ROWS: list[dict[str, Any]] = [
    {
        "id": "sql-name",
        "kind": "fact",
        "body": "User's name is Priya Shah.",
        "thread_id": "thread-ops-1",
        "confidence": 0.95,
        "day_offset": 1,
        "meta": {"topic": "identity"},
    },
    {
        "id": "sql-lang-stale",
        "kind": "preference",
        "body": "Priya prefers TypeScript for all backend work.",
        "thread_id": "thread-ops-1",
        "confidence": 0.7,
        "day_offset": 2,
        "meta": {"topic": "language", "status": "stale_candidate"},
    },
    {
        "id": "sql-timezone",
        "kind": "fact",
        "body": "Priya works in Asia/Kolkata (UTC+5:30).",
        "thread_id": "thread-ops-2",
        "confidence": 0.9,
        "day_offset": 15,
        "meta": {"topic": "timezone"},
    },
    {
        "id": "sql-ci",
        "kind": "instruction",
        "body": "CI must stay green on Python 3.11 and 3.12 before merge.",
        "thread_id": "thread-ops-2",
        "confidence": 0.88,
        "day_offset": 16,
        "meta": {"topic": "ci"},
    },
    {
        "id": "sql-oncall",
        "kind": "relationship",
        "body": "On-call buddy is Marcus Chen (Slack @marcus).",
        "thread_id": "thread-ops-3",
        "confidence": 0.92,
        "day_offset": 29,
        "meta": {"topic": "team"},
    },
    {
        "id": "sql-budget",
        "kind": "constraint",
        "body": "Monthly LLM spend budget is USD 200; alert Priya at 80%.",
        "thread_id": "thread-ops-3",
        "confidence": 0.9,
        "day_offset": 30,
        "meta": {"topic": "budget"},
    },
    {
        "id": "sql-runbook",
        "kind": "artifact",
        "body": (
            "Runbook path for pgbouncer incidents: "
            "docs/runbooks/pgbouncer-pool-exhaustion.md"
        ),
        "thread_id": "thread-ops-4",
        "confidence": 0.85,
        "day_offset": 22,
        "meta": {"topic": "runbook", "related_incident": "INC-441"},
    },
    {
        "id": "sql-commit",
        "kind": "commitment",
        "body": (
            "Priya committed to review the OKF migration PR within 24 hours of opening."
        ),
        "thread_id": "thread-ops-4",
        "confidence": 0.8,
        "day_offset": 36,
        "meta": {"topic": "review"},
    },
]


def seed_sqlite(db_path: Path, *, force: bool = False) -> dict[str, Any]:
    """Create/refresh the proprietary SQLite memory DB."""
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if force and db_path.exists():
        db_path.unlink()

    base = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_SCHEMA)
        conn.execute("DELETE FROM agent_memories")
        for row in _ROWS:
            when = base + timedelta(days=int(row["day_offset"]))
            stamp = when.isoformat().replace("+00:00", "Z")
            conn.execute(
                """
                INSERT INTO agent_memories
                (id, kind, body, thread_id, confidence, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["kind"],
                    row["body"],
                    row["thread_id"],
                    row["confidence"],
                    stamp,
                    stamp,
                    json.dumps(row["meta"]),
                ),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM agent_memories").fetchone()[0]

    report = {
        "backend": "sqlite3",
        "path": str(db_path),
        "table": "agent_memories",
        "count": count,
        "ids": [r["id"] for r in _ROWS],
    }
    (db_path.parent / "seed_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "data" / "sqlite" / "agent_memory.db"
    print(json.dumps(seed_sqlite(target, force=True), indent=2))

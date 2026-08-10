"""A realistic, time-evolving release-agent scenario for the live demo.

These are source conversations, not pre-extracted memories. Hindsight's retain
pipeline must extract, reconcile, link, and store the memory units itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEMO_BANK_ID = "beacon-release-copilot"

SESSIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "session-01-kickoff",
        "timestamp": "2026-07-06T09:00:00Z",
        "context": "Beacon release kickoff between Dana and the release copilot",
        "content": """
Dana: We are preparing the Helios API release named Beacon. The tentative
production window is Friday, July 31 at 14:00 UTC. Maya Chen is the release
DRI. The service runs PostgreSQL 16 and Redis 7.2.

Release Copilot: I recorded the tentative date, owner, and data-store versions.
I will keep an evidence-backed runbook as the plan evolves.
""",
    },
    {
        "id": "session-02-policy-correction",
        "timestamp": "2026-07-08T15:20:00Z",
        "context": "Dana corrects a scheduling conflict and sets reporting preferences",
        "content": """
Dana: Correction: we never deploy on Fridays. July 31 is cancelled. Move
Beacon to Tuesday, August 4, 2026 at 14:00 UTC. For release updates, use
Markdown with at most five bullets and no tables.

Release Copilot: I replaced the Friday date with Tuesday, August 4 at 14:00
UTC and will format future updates as requested.
""",
    },
    {
        "id": "session-03-staging-migration",
        "timestamp": "2026-07-13T11:45:00Z",
        "context": "The release copilot performs the first staging rehearsal",
        "content": """
Release Copilot: I ran the Beacon database migration in staging. The first run
failed because the pg_trgm extension was missing. I enabled pg_trgm, reran the
migration successfully in 3 minutes 42 seconds, and measured API p95 latency at
185 milliseconds. I added the PostgreSQL 16 pg_trgm preflight check to the
runbook.

Dana: Good. Keep that failed first attempt as evidence; do not erase it.
""",
    },
    {
        "id": "session-04-rollout-decision",
        "timestamp": "2026-07-16T16:10:00Z",
        "context": "The team chooses a canary and rollback policy",
        "content": """
Dana: Decision: start Beacon at a 10 percent canary for 30 minutes. Promote
only if the error rate stays below 1 percent and p95 latency remains below 250
milliseconds. Roll back immediately if either threshold is breached.

Release Copilot: I updated the go/no-go checklist with the 10 percent,
30-minute canary and both rollback thresholds.
""",
    },
    {
        "id": "session-05-owner-handoff",
        "timestamp": "2026-07-20T08:30:00Z",
        "context": "The original release owner hands off responsibility",
        "content": """
Dana: Maya will be on leave during the release. She is no longer the Beacon
DRI. Luis Ortega is the current release DRI, and Priya Shah is the backup.

Release Copilot: I replaced Maya with Luis as current DRI and listed Priya as
backup. The historical handoff remains in the audit trail.
""",
    },
    {
        "id": "session-06-cache-correction",
        "timestamp": "2026-07-21T13:05:00Z",
        "context": "A proposed cache setting is corrected before release",
        "content": """
Release Copilot: The draft runbook still says the new feature-flag cache TTL is
24 hours.

Dana: That draft value is wrong. The approved production TTL is 6 hours, not
24 hours. The shorter TTL is required so we can unwind the flag on the same
shift.

Release Copilot: Corrected. Six hours is now the approved value.
""",
    },
    {
        "id": "session-07-final-rehearsal",
        "timestamp": "2026-07-24T17:40:00Z",
        "context": "The release copilot completes the final rehearsal",
        "content": """
Release Copilot: I completed the final Beacon rehearsal using the current
runbook. The pg_trgm preflight passed, the migration completed in 3 minutes 39
seconds, the 10 percent canary simulation stayed at 0.3 percent errors, and p95
latency was 181 milliseconds. I verified Luis Ortega is DRI and Priya Shah is
backup for Tuesday, August 4 at 14:00 UTC.

Dana: Mark the rehearsal successful. The plan is ready.
""",
    },
    {
        "id": "session-08-current-truth",
        "timestamp": "2026-07-25T08:15:00Z",
        "context": "Dana signs off the current truth and identifies superseded values",
        "content": """
Dana: Final truth check: Beacon releases Tuesday, August 4 at 14:00 UTC with
Luis Ortega as DRI and Priya Shah as backup. We never deploy on Fridays. The
canary is 10 percent for 30 minutes; roll back above 1 percent errors or 250
milliseconds p95. The cache TTL is 6 hours. The old July 31 date, Maya-as-DRI,
and 24-hour TTL are superseded historical values and must not be used as the
current plan.

Release Copilot: I verified the current truth and will invalidate those three
superseded records while retaining them in Hindsight's curation archive.
""",
    },
)

GOLDEN_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "release-window",
        "question": "When is the current Beacon production release window?",
        "expected_groups": [["august 4"], ["14:00", "14:00 utc"]],
    },
    {
        "id": "release-owner",
        "question": "Who is the current Beacon release DRI and who is backup?",
        "expected_groups": [["luis ortega"], ["priya shah"]],
    },
    {
        "id": "database-preflight",
        "question": "What database prerequisite did staging reveal?",
        "expected_groups": [["postgresql 16", "postgres 16"], ["pg_trgm"]],
    },
    {
        "id": "canary-policy",
        "question": "What is the Beacon canary and rollback policy?",
        "expected_groups": [
            ["10 percent", "10%"],
            ["30 minutes", "30-minute"],
            ["1 percent", "1%"],
            ["250 milliseconds", "250 ms", "250ms"],
        ],
    },
    {
        "id": "cache-ttl",
        "question": "What is the approved feature-flag cache TTL?",
        "expected_groups": [["6 hours", "six hours"]],
    },
    {
        "id": "update-format",
        "question": "How should release updates be formatted?",
        "expected_groups": [
            ["markdown"],
            ["five bullets", "5 bullets"],
            ["no tables", "without tables"],
        ],
    },
    {
        "id": "staging-experience",
        "question": "What happened during the first staging migration rehearsal?",
        "expected_groups": [
            ["failed"],
            ["pg_trgm"],
            ["3 minutes 42 seconds", "3m42"],
            ["185 milliseconds", "185 ms"],
        ],
    },
    {
        "id": "friday-policy",
        "question": "What day-of-week deployment constraint applies?",
        "expected_groups": [
            [
                "never deploy on fridays",
                "never occur on fridays",
                "no friday",
                "not friday",
            ]
        ],
    },
)


def timestamp(value: str) -> datetime:
    """Parse one scenario timestamp into a timezone-aware datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def retain_items() -> list[dict[str, Any]]:
    """Build Hindsight retain items from the scripted source sessions."""
    return [
        {
            "content": session["content"].strip(),
            "timestamp": timestamp(session["timestamp"]),
            "context": session["context"],
            "document_id": session["id"],
            "metadata": {
                "scenario": "beacon-release",
                "session_id": session["id"],
                "source": "scripted-live-agent-run",
            },
            "tags": ["project:beacon", "demo:hindsight-okf"],
        }
        for session in SESSIONS
    ]

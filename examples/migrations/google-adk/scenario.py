"""A time-evolving Google ADK release-copilot scenario and golden recall set.

The turns are conversations. Durable state is written through ADK event
``state_delta`` actions, so the source SQLite database—not a fabricated export
file—is the authority the migration reads.
"""

from __future__ import annotations

from typing import Any

APP_NAME = "atlas-release-copilot"
USER_ID = "dana"

SESSIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "01-kickoff",
        "timestamp": "2026-07-06T09:00:00Z",
        "turns": (
            {
                "author": "user",
                "text": (
                    "We are preparing the Helios API release named Beacon. The "
                    "tentative production window is Friday, July 31 at 14:00 UTC. "
                    "Maya Chen is the release DRI. The service runs PostgreSQL 16 "
                    "and Redis 7.2."
                ),
            },
            {
                "author": "release_copilot",
                "text": "I recorded the tentative plan, owner, and platform stack.",
                "state_delta": {
                    "app:fact.project_stack": (
                        "Beacon is the Helios API release. It runs PostgreSQL 16 "
                        "and Redis 7.2."
                    ),
                    "app:goal.release_window": (
                        "The tentative Beacon production window is Friday, July 31, "
                        "2026 at 14:00 UTC."
                    ),
                    "app:relationship.release_ownership": (
                        "Maya Chen is the current Beacon release DRI."
                    ),
                },
            },
        ),
    },
    {
        "id": "02-schedule-correction",
        "timestamp": "2026-07-08T15:20:00Z",
        "turns": (
            {
                "author": "user",
                "text": (
                    "Correction: we never deploy on Fridays. July 31 is cancelled. "
                    "Move Beacon to Tuesday, August 4, 2026 at 14:00 UTC. For "
                    "release updates, use Markdown with at most five bullets and "
                    "no tables."
                ),
            },
            {
                "author": "release_copilot",
                "text": (
                    "I replaced the Friday date and saved your update format as a "
                    "user preference."
                ),
                "state_delta": {
                    "app:goal.release_window": (
                        "Beacon releases Tuesday, August 4, 2026 at 14:00 UTC."
                    ),
                    "app:instruction.deployment_calendar": (
                        "Beacon production deployments never occur on Fridays."
                    ),
                    "user:preference.release_update_format": (
                        "Dana prefers release updates in Markdown, with at most "
                        "five bullets and no tables."
                    ),
                },
            },
        ),
    },
    {
        "id": "03-staging-rehearsal",
        "timestamp": "2026-07-13T11:45:00Z",
        "turns": (
            {
                "author": "release_copilot",
                "text": (
                    "The first staging migration failed because pg_trgm was "
                    "missing. I enabled it, reran successfully in 3 minutes 42 "
                    "seconds, and measured 185 ms p95 latency."
                ),
                "state_delta": {
                    "app:learning.staging_database_preflight": (
                        "The first Beacon staging migration failed because the "
                        "PostgreSQL 16 pg_trgm extension was missing. After enabling "
                        "pg_trgm it succeeded in 3 minutes 42 seconds with 185 ms "
                        "p95 latency. The runbook now requires a pg_trgm preflight."
                    )
                },
            },
            {
                "author": "user",
                "text": "Keep the failed first attempt as evidence; do not erase it.",
            },
        ),
    },
    {
        "id": "04-rollout-policy",
        "timestamp": "2026-07-16T16:10:00Z",
        "turns": (
            {
                "author": "user",
                "text": (
                    "Decision: start at a 10 percent canary for 30 minutes. Promote "
                    "only below 1 percent errors and below 250 ms p95. Roll back "
                    "immediately if either threshold is breached."
                ),
            },
            {
                "author": "release_copilot",
                "text": "The canary and rollback decision is in the durable runbook state.",
                "state_delta": {
                    "app:decision.canary_and_rollback": (
                        "Beacon starts at a 10 percent canary for 30 minutes. "
                        "Promote only while errors remain below 1 percent and p95 "
                        "latency remains below 250 ms; otherwise roll back immediately."
                    )
                },
            },
        ),
    },
    {
        "id": "05-owner-handoff",
        "timestamp": "2026-07-20T08:30:00Z",
        "turns": (
            {
                "author": "user",
                "text": (
                    "Maya will be on leave during release and is no longer the DRI. "
                    "Luis Ortega is the current release DRI; Priya Shah is backup."
                ),
            },
            {
                "author": "release_copilot",
                "text": "I replaced the owner while retaining the handoff in the event log.",
                "state_delta": {
                    "app:relationship.release_ownership": (
                        "Luis Ortega is the current Beacon release DRI, and Priya "
                        "Shah is the backup."
                    )
                },
            },
        ),
    },
    {
        "id": "06-cache-correction",
        "timestamp": "2026-07-21T13:05:00Z",
        "turns": (
            {
                "author": "release_copilot",
                "text": "The draft runbook says the feature-flag cache TTL is 24 hours.",
                "state_delta": {
                    "app:decision.feature_flag_cache_ttl": (
                        "The draft Beacon feature-flag cache TTL is 24 hours."
                    )
                },
            },
            {
                "author": "user",
                "text": (
                    "That draft is wrong. The approved production TTL is 6 hours, "
                    "not 24, so we can unwind the flag on the same shift."
                ),
            },
            {
                "author": "release_copilot",
                "text": "Corrected: six hours is now the approved current value.",
                "state_delta": {
                    "app:decision.feature_flag_cache_ttl": (
                        "The approved Beacon production feature-flag cache TTL is 6 "
                        "hours so the flag can be unwound on the same shift."
                    )
                },
            },
        ),
    },
    {
        "id": "07-final-rehearsal",
        "timestamp": "2026-07-24T17:40:00Z",
        "turns": (
            {
                "author": "release_copilot",
                "text": (
                    "The final rehearsal passed: pg_trgm preflight succeeded, the "
                    "migration took 3 minutes 39 seconds, the canary simulation had "
                    "0.3 percent errors, and p95 was 181 ms."
                ),
                "state_delta": {
                    "app:event.final_rehearsal": (
                        "Beacon's final rehearsal succeeded on July 24, 2026. The "
                        "pg_trgm preflight passed, migration took 3 minutes 39 "
                        "seconds, canary errors were 0.3 percent, and p95 latency "
                        "was 181 ms."
                    ),
                    "app:commitment.release_readiness": (
                        "Beacon is ready for its approved August 4 release plan."
                    ),
                },
            },
            {
                "author": "user",
                "text": "Mark the rehearsal successful and the plan ready.",
            },
        ),
    },
    {
        "id": "08-current-truth",
        "timestamp": "2026-07-25T08:15:00Z",
        "turns": (
            {
                "author": "user",
                "text": (
                    "Final truth check: August 4 at 14:00 UTC, Luis as DRI, Priya "
                    "as backup, 10 percent canary for 30 minutes, rollback at 1 "
                    "percent errors or 250 ms p95, and 6-hour TTL. The July 31 "
                    "date, Maya-as-DRI, and 24-hour TTL are superseded."
                ),
            },
            {
                "author": "release_copilot",
                "text": "Verified. Current state and historical event evidence agree.",
            },
        ),
    },
)


GOLDEN_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "release-window",
        "question": "When is the current Beacon production release window?",
        "expected_groups": (("august 4",), ("14:00", "14:00 utc")),
    },
    {
        "id": "release-owner",
        "question": "Who is the current Beacon release DRI and who is backup?",
        "expected_groups": (("luis ortega",), ("priya shah",)),
    },
    {
        "id": "deployment-calendar",
        "question": "What day-of-week deployment rule applies to Beacon?",
        "expected_groups": (("never occur on fridays", "never deploy on fridays"),),
    },
    {
        "id": "update-format",
        "question": "How should Dana's release updates be formatted?",
        "expected_groups": (
            ("markdown",),
            ("five bullets", "5 bullets"),
            ("no tables", "without tables"),
        ),
    },
    {
        "id": "database-preflight",
        "question": "What database prerequisite did staging reveal?",
        "expected_groups": (("postgresql 16",), ("pg_trgm",)),
    },
    {
        "id": "canary-policy",
        "question": "What is the Beacon canary and rollback policy?",
        "expected_groups": (
            ("10 percent", "10%"),
            ("30 minutes", "30-minute"),
            ("1 percent", "1%"),
            ("250 ms", "250 milliseconds"),
        ),
    },
    {
        "id": "cache-ttl",
        "question": "What is the approved feature-flag cache TTL?",
        "expected_groups": (("6 hours", "six hours"),),
    },
    {
        "id": "final-rehearsal",
        "question": "What were the final Beacon rehearsal results?",
        "expected_groups": (
            ("succeeded", "successful", "passed"),
            ("3 minutes 39 seconds",),
            ("0.3 percent", "0.3%"),
            ("181 ms", "181 milliseconds"),
        ),
    },
)

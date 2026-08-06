"""The source conversation fed into Graphiti.

This is not a memory dump -- it is the *input* to a real Graphiti run. Every
fact, entity and temporal edge in ``data/graphiti_raw_export.json`` is produced
by Graphiti's own extraction pipeline reading these episodes; nothing in the
export is hand-authored.

The script is written to exercise the one thing that makes Graphiti worth
migrating carefully: bi-temporality. Across seven months the same speaker
contradicts himself six separate times, so a correct migration has to keep both
the old and the new value of each fact *and* know which is which:

===================  ==========================  ==========================
What changes         Original (session/date)     Replacement (session/date)
===================  ==========================  ==========================
Primary datastore    Postgres      (S1, Jan)     ClickHouse    (S3, Mar)
IaC tool             Terraform     (S2, Feb)     Pulumi        (S4, May)
Cloud region         eu-west-1     (S1, Jan)     us-east-1     (S4, May)
Team size            4 engineers   (S1, Jan)     9 engineers   (S4, May)
Employer             Northwind     (S1, Jan)     Halcyon Data  (S5, Jun)
Beta ship date       end of Q1     (S2, Feb)     Q2            (S3, Mar)
===================  ==========================  ==========================

Those six reversals are what the golden Q&A set in :mod:`graphiti_okf.golden_qa`
probes, and they are the reason ``valid_at``/``invalid_at`` must survive the
migration instead of being flattened into a single ``created_at``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Episode:
    """One conversational turn, timestamped as it would have happened."""

    name: str
    body: str
    source_description: str
    reference_time: datetime


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


EPISODES: tuple[Episode, ...] = (
    Episode(
        name="s1-kickoff",
        source_description="project kickoff chat",
        reference_time=_ts(2026, 1, 14, 9, 30),
        body=(
            "user: Kicking off the Atlas project today. I'm Daniel Okafor, staff engineer "
            "at Northwind Analytics. We're building a customer-facing analytics product.\n"
            "assistant: Congratulations on the kickoff. What does the stack look like?\n"
            "user: Postgres is our primary datastore — everything goes through it for now. "
            "I prefer Postgres because the team already knows it well. Backend is Python, "
            "and we test with pytest. We're deploying to AWS in eu-west-1. Small team, "
            "just 4 engineers including me."
        ),
    ),
    Episode(
        name="s1-conventions",
        source_description="project kickoff chat",
        reference_time=_ts(2026, 1, 14, 10, 15),
        body=(
            "user: One more thing on conventions — I strongly prefer typed Python. "
            "Everything gets type hints, and we run mypy in CI. No exceptions.\n"
            "assistant: Noted. Any preference on code review process?\n"
            "user: Keep PRs under 400 lines. I care about that more than almost anything "
            "else on process."
        ),
    ),
    Episode(
        name="s2-infra",
        source_description="infrastructure planning session",
        reference_time=_ts(2026, 2, 20, 14, 0),
        body=(
            "user: Infrastructure decision time. We've decided on Terraform for "
            "infrastructure as code — the team voted and Terraform won.\n"
            "assistant: Makes sense. What about caching?\n"
            "user: Adding Redis for the caching layer. Also our goal is to ship the v1 "
            "beta by the end of Q1. We're doing trunk-based development, no long-lived "
            "feature branches."
        ),
    ),
    Episode(
        name="s3-datastore-change",
        source_description="architecture review",
        reference_time=_ts(2026, 3, 30, 11, 0),
        body=(
            "user: Big change. We've moved off Postgres as our primary datastore — "
            "the analytics queries were falling over at our data volume. We're on "
            "ClickHouse now. Postgres stays, but only for auth and user accounts.\n"
            "assistant: That's a significant migration. Does it affect the timeline?\n"
            "user: Yes, unfortunately. The beta is slipping — we're now targeting Q2, "
            "not the end of Q1 like I said in February."
        ),
    ),
    Episode(
        name="s4-tooling-reversal",
        source_description="platform team sync",
        reference_time=_ts(2026, 5, 11, 16, 30),
        body=(
            "user: I need to walk something back. I used to prefer Terraform, but I've "
            "changed my mind — we've switched to Pulumi. Being able to write "
            "infrastructure in real Python won the argument.\n"
            "assistant: Understood, Pulumi it is. Anything else changed?\n"
            "user: Two things. We moved our region from eu-west-1 to us-east-1 because "
            "most of our customers are in North America and the latency was hurting. "
            "And the team has grown — we're 9 engineers now, up from 4."
        ),
    ),
    Episode(
        name="s5-job-change",
        source_description="career catch-up",
        reference_time=_ts(2026, 6, 25, 8, 45),
        body=(
            "user: Personal news — I've left Northwind Analytics. I'm now a principal "
            "engineer at Halcyon Data, starting this month.\n"
            "assistant: Congratulations. Are you still working on Atlas?\n"
            "user: Yes, Halcyon acquired the team. Still Python, but we've switched "
            "package management from poetry to uv. Much faster."
        ),
    ),
    Episode(
        name="s5-incident",
        source_description="incident retrospective",
        reference_time=_ts(2026, 6, 29, 19, 20),
        body=(
            "user: We had an incident last night. ClickHouse ran out of disk during a "
            "historical backfill and the ingest pipeline stalled for about six hours.\n"
            "assistant: What was the resolution?\n"
            "user: We expanded the volume and added a disk-usage alert at 75%. Lesson "
            "learned: always size backfill headroom before starting one."
        ),
    ),
    Episode(
        name="s6-current-state",
        source_description="quarterly planning",
        reference_time=_ts(2026, 7, 30, 13, 0),
        body=(
            "user: Quarterly planning. v1 shipped in Q2 as promised after the slip. "
            "We've now committed to completing a SOC 2 Type II audit by October.\n"
            "assistant: Where does the stack stand today?\n"
            "user: ClickHouse for analytics, Postgres for auth, Redis for cache, Pulumi "
            "for infrastructure, all in us-east-1. Still Python, still typed, still "
            "trunk-based. I'm happy with where we landed."
        ),
    ),
)


def episode_count() -> int:
    return len(EPISODES)


def session_span() -> tuple[datetime, datetime]:
    """Earliest and latest reference times, for the run summary."""
    times = [episode.reference_time for episode in EPISODES]
    return min(times), max(times)

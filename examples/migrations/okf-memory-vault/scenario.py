"""scenario.py - The demo story: a lived-in agent memory vault for "Lumenly".

Lumenly is a fictional AI customer-support analytics SaaS built by an indie
developer named Maya. Her agent helper keeps its working memory in an OKF
bundle, versioned in git, synced from Memanto. The sessions below are the
*output* of real agent sessions (recalled preferences, corrections, decisions)
rendered as OKF markdown - the exact format ``memanto memory sync --okf``
writes and ``memanto migrate okf`` reads.

The point of the story: once memory is portable markdown, it gets a *life*.
Memory is born (seed), evolves (preference corrections), collides (two agents
disagree on a fact), gets audited and fixed (bad memory rolled back), and is
reviewed by humans like code. None of that is possible when memory is trapped
in a proprietary store.

Each session below lists the *full* set of memories after that session, plus a
short narrative of what changed and why. ``run.py`` renders these snapshots
into real OKF bundles and drives the git + diff workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from okf_bundle import Memory

MEM = "Lumenly Agent"


def mem(
    type_: str,
    title: str,
    body: str,
    ts: str,
    description: str = "",
    tags: list[str] | None = None,
    resource: str = "",
    confidence: float | None = None,
    status: str = "active",
    provenance: str = "agent_session",
) -> Memory:
    xm: dict[str, Any] = {"status": status, "provenance": provenance}
    if confidence is not None:
        xm["confidence"] = confidence
    return Memory(
        type=type_,
        title=title,
        body=body,
        timestamp=ts,
        description=description,
        tags=tags or [],
        resource=resource,
        x_memanto=xm,
    )


# ---------------------------------------------------------------------------
# Session snapshots
# ---------------------------------------------------------------------------

S1_BASELINE = [
    # --- instruction ------------------------------------------------------
    mem("instruction", "Every PR must include tests for new modules",
        "CI fails if a PR touches a Python or TypeScript module without adding "
        "or updating tests. No exceptions for 'small' changes.\n\n"
        "Rationale: the product is 90% logic; untested logic is how customer "
        "support answers go wrong.",
        "2026-08-02T10:15:00Z", tags=["ci", "testing"], confidence=0.98),
    mem("instruction", "Never commit .env files - use Doppler for secrets",
        "Secrets live in Doppler. Local development uses `.env.example` with "
        "placeholder values only. If a real secret appears in a diff, rotate it "
        "immediately and post in #security.",
        "2026-08-02T10:16:00Z", tags=["security", "secrets"], confidence=0.99),
    mem("instruction", "Keep public API backward compatible for one release cycle",
        "Breaking changes to the public REST API must be deprecated for one full "
        "release cycle first. Document the deprecation in the changelog and in "
        "`docs/api.md`.",
        "2026-08-03T09:30:00Z", tags=["api", "compatibility"], confidence=0.95),
    mem("instruction", "Deploy only after green CI on main",
        "No direct pushes to main. Merges require at least one review, green CI, "
        "and a passing `memanto migrate okf --dry-run` when memory schemas change.",
        "2026-08-05T14:00:00Z", tags=["deploy", "ci"], confidence=0.97),
    # --- fact -------------------------------------------------------------
    mem("fact", "Lumenly's stack is FastAPI + React + PostgreSQL on Fly.io",
        "Backend: FastAPI (Python 3.12). Frontend: React + TypeScript. Database: "
        "PostgreSQL 16. Hosting: Fly.io (LAX + IAD regions). Analytics pipeline "
        "is a background worker on the same app.",
        "2026-08-02T11:00:00Z", tags=["stack", "infra"], confidence=0.99),
    mem("fact", "Maya's timezone is UTC-7 (Pacific)",
        "Maya works from Portland, OR. Demo hours: 10:00-18:00 Pacific. Friday "
        "afternoons are blocked for deep work.",
        "2026-08-03T10:00:00Z", tags=["people", "schedule"], confidence=0.98),
    mem("fact", "Free tier limit is 500 events per month",
        "Free accounts ingest up to 500 support events/month. Over-limit events "
        "are held for 7 days, then dropped unless the account upgrades.",
        "2026-08-04T13:20:00Z", tags=["product", "pricing"], confidence=0.96),
    mem("fact", "Maya's birthday is September 2",
        "Maya's birthday is September 2 (not August). Celebrate with a cake emoji "
        "in the team channel on that day.",
        "2026-08-06T16:45:00Z", tags=["people"], confidence=0.99, provenance="manual"),
    # --- decision ---------------------------------------------------------
    mem("decision", "Chose PostgreSQL over MongoDB for analytics storage",
        "We need transactional guarantees across events + billing. PostgreSQL 16 "
        "with JSONB covers flexible event shapes; MongoDB's flexible schema did "
        "not justify the operational cost.",
        "2026-08-07T09:00:00Z", tags=["database", "architecture"], confidence=0.98),
    mem("decision", "Adopted semantic versioning for the public API",
        "`/api/v1` follows semver. Breaking changes bump the major version; "
        "backward-compatible additions bump minor. Changelog is generated from "
        "conventional commits.",
        "2026-08-07T09:30:00Z", tags=["api", "versioning"], confidence=0.97),
    # --- goal -------------------------------------------------------------
    mem("goal", "Reach 100 paying customers by the Q3 review",
        "Current: 34 paying customers (Aug 18). Gap: 66. Main levers: onboarding "
        "conversion (currently 18%), the data-export feature (top request), and "
        "the new lifecycle email sequence.",
        "2026-08-08T15:00:00Z", tags=["growth"], confidence=0.9),
    # --- commitment -------------------------------------------------------
    mem("commitment", "Ship onboarding flow before the Friday demo",
        "Maya promised the design partner Alex the new onboarding flow would be "
        "demo-ready by Friday. Milestones: Wednesday - wizard screens, Thursday - "
        "Postgres wiring, Friday morning - polish.",
        "2026-08-09T11:00:00Z", tags=["onboarding", "demo"], confidence=0.92),
    # --- preference -------------------------------------------------------
    mem("preference", "Maya prefers short code review comments over long threads",
        "Review comments should be one actionable sentence with a file:line "
        "reference. If a discussion goes past three comments, move it to a "
        "sync-up instead of a thread.",
        "2026-08-02T12:00:00Z", tags=["reviews", "communication"], confidence=0.93),
    mem("preference", "Maya likes weekly async updates instead of daily standups",
        "No daily standup. Fridays get a 5-bullet async update: shipped, blocked, "
        "next, risks, asks. Keep it under 100 words.",
        "2026-08-03T10:30:00Z", tags=["communication", "rituals"], confidence=0.94),
    mem("preference", "Maya prefers detailed engineering docs for every feature",
        "Each feature ships with a design doc covering context, options considered, "
        "and trade-offs. Docs live in `docs/features/`.",
        "2026-08-05T09:15:00Z", tags=["docs"], confidence=0.9),
    # --- relationship -----------------------------------------------------
    mem("relationship", "Alex reviews every UI change before release",
        "Alex is the design partner. Every user-facing change needs a sign-off "
        "from Alex before it ships. Loop Alex in on PRs touching the frontend.",
        "2026-08-06T10:00:00Z", tags=["people", "ui"], confidence=0.95),
    # --- context ----------------------------------------------------------
    mem("context", "Current sprint focus: onboarding + billing",
        "Sprint 8: (1) onboarding wizard, (2) Stripe billing for annual plans, "
        "(3) analytics batching fix. Everything else is parked.",
        "2026-08-09T12:00:00Z", tags=["sprint"], confidence=0.9),
    # --- event ------------------------------------------------------------
    mem("event", "First paying customer (Northwind Labs) signed on Aug 14",
        "Northwind Labs upgraded to the Team plan after a 3-week trial. They "
        "cited data export and Slack alerts as the deciding features.",
        "2026-08-14T20:10:00Z", tags=["customers", "milestone"], confidence=0.99),
    # --- learning ---------------------------------------------------------
    mem("learning", "Customers ask about data export most often - treat as feature signal",
        "Across 14 onboarding calls, data export came up 11 times. The feature "
        "was already on the roadmap; the signal says it should be a first-class "
        "marketing angle too.",
        "2026-08-16T17:00:00Z", tags=["product", "research"], confidence=0.88),
    # --- artifact ---------------------------------------------------------
    mem("artifact", "API reference lives in docs/api.md",
        "Generated from the OpenAPI spec on every release. Human-written notes "
        "go in `docs/api-guide.md`.",
        "2026-08-04T14:00:00Z", tags=["docs", "api"], confidence=0.99),
]

S2_EVOLVE = [
    # Free tier fact is *modified in place* (same title/slug, updated content).
    mem("fact", "Free tier limit is 500 events per month",
        "Free accounts ingest up to 500 support events/month. Over-limit events "
        "are held for 7 days, then dropped unless the account upgrades. Raised "
        "from 250 on Aug 18 after the pricing review - the 250 cap caused two "
        "trial churns.",
        "2026-08-04T13:20:00Z", tags=["product", "pricing", "change"], confidence=0.98),
    *[m for m in S1_BASELINE if m.title != "Free tier limit is 500 events per month"],
    mem("preference", "Maya now prefers concise docs: README + one ADR per significant decision",
        "Maya changed her mind (Aug 19): 'the design docs are too long, nobody "
        "reads them.' Going forward: README sections + one ADR per significant "
        "decision. Old design docs stay for history but are no longer required.",
        "2026-08-19T15:30:00Z", tags=["docs"], confidence=0.95,
        provenance="correction", status="supersedes:preference/maya-prefers-detailed-engineering-docs-for-every-feature"),
    mem("fact", "Analytics events are batched every 15 minutes",
        "The worker flushes analytics events in 15-minute batches to keep "
        "Postgres write volume low. Batch size is configurable via "
        "`ANALYTICS_BATCH_MINUTES`.",
        "2026-08-20T09:00:00Z", tags=["analytics", "infra"], confidence=0.94),
    mem("instruction", "PII fields must be pseudonymized before analytics",
        "Customer emails and names are hashed with HMAC-SHA256 before entering "
        "the analytics pipeline. Raw PII never touches the events table.",
        "2026-08-20T09:20:00Z", tags=["privacy", "security"], confidence=0.97),
    mem("event", "Onboarding funnel conversion improved to 34% after redesign",
        "The onboarding wizard redesign lifted activation from 18% to 34% "
        "(measured Aug 20-23, n=212 trials). Main driver: the 'connect your "
        "support inbox' step moved from step 4 to step 1.",
        "2026-08-23T18:00:00Z", tags=["onboarding", "metrics"], confidence=0.91),
]

S3_CONFLICT = S2_EVOLVE + [
    mem("fact", "Average customer response time is 1.8 hours",
        "Measured over the last 30 days across 4,120 conversations: median first "
        "response is 1.8h. Faster in EU (1.2h), slower in APAC (3.1h).",
        "2026-08-24T08:30:00Z", tags=["metrics", "support"], confidence=0.87,
        provenance="main_agent"),
    mem("fact", "Average customer response time is 4.2 hours",
        "Nightly analytics run (Aug 24) reports median first response at 4.2h. "
        "The APAC queue has a 6h backlog after the Aug 22 incident.",
        "2026-08-24T02:00:00Z", tags=["metrics", "support"], confidence=0.9,
        provenance="nightly_analytics"),
    mem("fact", "Maya's birthday is August 15",
        "Pulled from the old team profile spreadsheet during the migration "
        "cleanup. Note: conflicts with an earlier memory - verify before use.",
        "2026-08-25T11:00:00Z", tags=["people"], confidence=0.6,
        provenance="nightly_analytics"),
    mem("goal", "Cut p95 API latency under 250ms",
        "p95 is currently 410ms (Aug 24). Target: <250ms by Sept 15. Suspected "
        "cause: N+1 queries in the events endpoint.",
        "2026-08-25T13:00:00Z", tags=["performance"], confidence=0.85),
    mem("commitment", "Send a changelog to customers every two weeks",
        "Maya committed to a bi-weekly customer changelog email starting Sep 1. "
        "First issue covers onboarding + data export preview.",
        "2026-08-25T15:00:00Z", tags=["customers", "communication"], confidence=0.93),
]

# Titles that the human review removes in v4 (reverted like a bad PR).
_REVERTED_V3_TITLES = {
    "Maya's birthday is August 15",
    "Average customer response time is 1.8 hours",
    "Average customer response time is 4.2 hours",
}


def _replaced(memories: list[Memory], title: str, replacement: Memory) -> list[Memory]:
    """Return a new list with the memory of ``title`` replaced (in place)."""
    return [replacement if m.title == title else m for m in memories]


S4_RESOLVED = _replaced(
    _replaced(
        [m for m in S3_CONFLICT if m.title not in _REVERTED_V3_TITLES],
        "Maya's birthday is September 2",
        mem("fact", "Maya's birthday is September 2",
            "Maya's birthday is September 2 (not August). Confirmed directly "
            "with Maya on Aug 26 - the 'August 15' entry was a 2024 spreadsheet "
            "typo imported during cleanup and has been reverted.",
            "2026-08-06T16:45:00Z", tags=["people"], confidence=0.99,
            provenance="human_review"),
    ),
    "Cut p95 API latency under 250ms",
    mem("goal", "Cut p95 API latency under 250ms",
        "p95 was 410ms (Aug 24), now 320ms (Aug 26) after fixing the N+1 "
        "queries in the events endpoint. Remaining work: query planner for the "
        "analytics rollups. Target: <250ms by Sept 15.",
        "2026-08-25T13:00:00Z", tags=["performance"], confidence=0.9),
) + [
    mem("fact", "Average customer response time is 2.9 hours (resolved)",
        "Reconciliation (Aug 26): the 1.8h figure excluded APAC; the 4.2h "
        "figure included the Aug 22 incident backlog. Blended median is 2.9h. "
        "Going forward, the nightly analytics agent owns this metric and the "
        "main agent reads it, not writes it.",
        "2026-08-26T09:00:00Z", tags=["metrics", "support"], confidence=0.95,
        provenance="human_review", status="resolution"),
]

SESSION_NARRATIVES = {
    "v1": {
        "name": "Session 1-2: The seed",
        "narrative": (
            "The agent spends its first two weeks absorbing Maya's world: her stack, "
            "her preferences, the decisions the team made, the first customer. All of "
            "it lands in one git-versioned OKF bundle - plain markdown, one memory "
            "per file, readable by any human or tool."
        ),
    },
    "v2": {
        "name": "Session 3: Memory evolves",
        "narrative": (
            "Maya changes her mind about docs. The old preference is superseded by a "
            "correction. A normal day for a living memory - and now the change is a "
            "reviewable diff, not an opaque DB row overwrite."
        ),
    },
    "v3": {
        "name": "Session 4: Two agents collide",
        "narrative": (
            "The main agent and the nightly analytics agent disagree on a metric, and "
            "a cleanup job imports a wrong birthday. Contradictions are now *visible*: "
            "they show up in the diff as competing entries instead of silently "
            "clobbering each other in a vector store."
        ),
    },
    "v4": {
        "name": "Session 5: Human review + rollback",
        "narrative": (
            "Maya reviews the vault like a code review. The wrong birthday entry is "
            "reverted, the response-time contradiction is resolved with a single "
            "source of truth, and the whole audit trail lives in git log."
        ),
    },
}

# Names of files removed between v3 and v4 (for the rollback demo).
REVERTED_ENTRY = "memories/fact/maya-s-birthday-is-august-15.md"

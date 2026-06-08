"""Benchmark dataset: 6 complex scenarios with evolving preferences.

Each scenario:
  - history: list of ingestion turns (ordered oldest → newest)
  - probes: list of (query, expected_keyword, reasoning) tuples
    * expected_keyword: word that MUST appear in the answer for a correct response
    * reasoning: why this is the ground truth

Design principles:
  1. Every scenario has at least one PREFERENCE REVERSAL to test
     whether stale facts are purged or contaminate retrieval.
  2. Scenarios span multiple domains so slot detection is challenged.
  3. Probes ask for the CURRENT preference — not historical state.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Probe:
    query: str
    expected_keyword: str
    explanation: str
    stale_keyword: str | None = None  # if present in context, penalise (stale contamination)


@dataclass
class Scenario:
    name: str
    description: str
    history: list[str]
    probes: list[Probe]


SCENARIOS: list[Scenario] = [
    # ------------------------------------------------------------------
    # 1. Report format evolution
    # ------------------------------------------------------------------
    Scenario(
        name="report-format-reversal",
        description=(
            "User starts requesting concise executive briefs then pivots to "
            "detailed launch-risk memos mid-project."
        ),
        history=[
            "Always format my reports as concise executive briefs — one page max.",
            "Q2 revenue: $1.2M, churn 4%, NPS 62.",
            "Team headcount grew from 18 to 24 engineers.",
            "Our product just entered beta. From now on I need detailed launch-risk memos "
            "with evidence tables and risk ratings — not the old brief format.",
            "Beta DAU: 340, p99 latency 420ms, 3 critical bugs open.",
        ],
        probes=[
            Probe(
                query="How should I format the launch-risk report for the board?",
                expected_keyword="memo",
                stale_keyword="brief",
                explanation="Latest instruction overrides: detailed launch-risk memo, not brief.",
            ),
            Probe(
                query="What report format does the user prefer for product updates?",
                expected_keyword="evidence",
                stale_keyword="brief",
                explanation="Evidence tables are now required per latest instruction.",
            ),
        ],
    ),

    # ------------------------------------------------------------------
    # 2. Timezone policy flip
    # ------------------------------------------------------------------
    Scenario(
        name="timezone-policy-flip",
        description=(
            "Engineering team initially uses UTC everywhere, then switches to "
            "customer-facing local timezone after international expansion."
        ),
        history=[
            "All timestamps in our system must use UTC. Never localise.",
            "We launched in Germany. US HQ in UTC-5, Germany in CET (UTC+1).",
            "Our German customers complained that timestamps are confusing.",
            "Decision: all customer-facing dates must be shown in the customer's "
            "local timezone. Internal engineering logs keep UTC.",
        ],
        probes=[
            Probe(
                query="What timezone should customer invoice dates use?",
                expected_keyword="local",
                stale_keyword="never",
                explanation="Latest policy: customer-facing = local timezone.",
            ),
            Probe(
                query="What timezone should internal system logs use?",
                expected_keyword="utc",
                explanation="Engineering logs stay UTC per decision.",
            ),
        ],
    ),

    # ------------------------------------------------------------------
    # 3. Payment retry strategy overhaul
    # ------------------------------------------------------------------
    Scenario(
        name="payment-retry-overhaul",
        description=(
            "Engineering team iterates through three payment retry strategies "
            "before settling on advisory lock + outbox pattern."
        ),
        history=[
            "For failed payments: exponential backoff, max 5 retries, at-most-once semantics.",
            "We had a double-charge incident. Moving to at-least-once with idempotency keys.",
            "Still seeing duplicate charges under high load. New approach: advisory lock on "
            "payment_id before processing, combined with transactional outbox event for retry.",
            "Rollback plan: if advisory lock unavailable, fail fast and alert ops.",
        ],
        probes=[
            Probe(
                query="What is the current payment retry strategy?",
                expected_keyword="advisory",
                stale_keyword="exponential",
                explanation="Final strategy: advisory lock + outbox event.",
            ),
            Probe(
                query="What should we do if the advisory lock is unavailable?",
                expected_keyword="fail",
                explanation="Rollback plan: fail fast and alert ops.",
            ),
        ],
    ),

    # ------------------------------------------------------------------
    # 4. Investor update style conflict
    # ------------------------------------------------------------------
    Scenario(
        name="investor-update-style",
        description=(
            "CEO changes investor update priorities three times as company "
            "shifts from growth to revenue metrics."
        ),
        history=[
            "Lead investor updates with user growth numbers — that's our north star.",
            "Investor meeting feedback: they want ARR first, then growth.",
            "Series B closing soon. New guidance: lead with ARR, highlight churn reduction. "
            "Growth is secondary. Investors now care about path to profitability.",
            "ARR is $4.2M, churn dropped from 6% to 3.8% this quarter.",
        ],
        probes=[
            Probe(
                query="What metric should lead the investor update?",
                expected_keyword="arr",
                stale_keyword="growth",
                explanation="Latest instruction: ARR first, not growth.",
            ),
            Probe(
                query="What is the current ARR?",
                expected_keyword="4.2",
                explanation="ARR = $4.2M per latest fact.",
            ),
        ],
    ),

    # ------------------------------------------------------------------
    # 5. Engineering ticket template evolution
    # ------------------------------------------------------------------
    Scenario(
        name="engineering-ticket-template",
        description=(
            "Team iterates on incident ticket format after two post-mortems "
            "reveal incomplete root-cause analysis."
        ),
        history=[
            "Engineering tickets must include: title, description, acceptance criteria.",
            "After last P0: add rollback plan section to every critical ticket.",
            "After second incident: P0 tickets now require — root cause hypothesis, "
            "impact radius estimate, rollback plan, and owner sign-off.",
            "Non-P0 tickets still just need title, description, acceptance criteria.",
        ],
        probes=[
            Probe(
                query="What sections are required in a P0 engineering ticket?",
                expected_keyword="rollback",
                explanation="P0 requires rollback plan per latest template.",
            ),
            Probe(
                query="What sections are required in a regular non-P0 ticket?",
                expected_keyword="acceptance",
                explanation="Non-P0: title, description, acceptance criteria only.",
            ),
        ],
    ),

    # ------------------------------------------------------------------
    # 6. Evidence standard — cross-domain multi-session
    # ------------------------------------------------------------------
    Scenario(
        name="evidence-standard-cross-session",
        description=(
            "User establishes a no-speculation rule after one bad quarterly forecast, "
            "then adds citation requirement after a board challenge."
        ),
        history=[
            "In Q3 forecast we speculated on pipeline. It was wrong.",
            "From now on: no speculative roadmap items in any report. Only observed evidence.",
            "Board challenged our competitive analysis — they wanted sources.",
            "New rule: all competitive claims must cite sources (link or publication date). "
            "The no-speculation rule still applies to roadmaps.",
            "New product roadmap draft ready for review.",
        ],
        probes=[
            Probe(
                query="Can we include speculative roadmap items in the Q4 report?",
                expected_keyword="no",
                stale_keyword="speculative",
                explanation="Rule: no speculation — only observed evidence.",
            ),
            Probe(
                query="What evidence standard applies to competitive claims?",
                expected_keyword="cite",
                explanation="Competitive claims must cite sources.",
            ),
        ],
    ),
]

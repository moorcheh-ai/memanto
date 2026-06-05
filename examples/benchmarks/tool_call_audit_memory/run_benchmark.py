#!/usr/bin/env python3
"""Tool-call audit memory benchmark for the Memanto showdown.

The benchmark is intentionally offline and deterministic. It models a coding
agent that accumulates noisy tool output, user constraints, stale decisions,
review feedback, payout state, and secret-shaped values over a long session.
The active memory backend is a small Memanto-style digest that keeps typed,
current facts and redacts secrets before retrieval.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SECRET_PATTERNS = [
    re.compile(r"stripe_live_secret_[A-Za-z0-9_]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text


def leaks_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
        if token
        not in {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "should",
            "which",
            "what",
        }
    }


def token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


@dataclass(frozen=True)
class Fact:
    key: str
    value: str
    tags: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class AuditEvent:
    session: str
    source: str
    text: str
    facts: tuple[Fact, ...] = ()


@dataclass(frozen=True)
class Query:
    question: str
    must_have: tuple[str, ...]
    must_not_have: tuple[str, ...] = ()


EVENTS: tuple[AuditEvent, ...] = (
    AuditEvent(
        "s01",
        "user",
        "User allowed revenue-related Gmail review only. They also asked to avoid "
        "posting sensitive payment details unless confirmed for a specific platform.",
        (
            Fact(
                "gmail.scope",
                "Read only revenue-related Gmail threads; do not inspect unrelated mail.",
                ("gmail", "permission", "privacy"),
                "User constrained mailbox access to revenue-related messages.",
            ),
            Fact(
                "payment.public_qr",
                "Do not post payment QR or sensitive payout details to third-party platforms without explicit confirmation.",
                ("payment", "privacy", "bounty"),
                "Payment details must stay private unless confirmed per platform.",
            ),
        ),
    ),
    AuditEvent(
        "s02",
        "tool",
        "Audit found a Stripe secret in .env: STRIPE_SECRET_KEY=stripe_live_secret_FAKE_TOOL_AUDIT_0000. "
        "The value was removed from logs before sharing.",
        (
            Fact(
                "secret.stripe",
                "A Stripe secret was observed and must be represented only as <redacted>.",
                ("secret", "audit", "stripe"),
                "Secret-shaped values must never be injected verbatim.",
            ),
        ),
    ),
    AuditEvent(
        "s03",
        "implementation",
        "Auth middleware decision: verified JWT payloads must contain a non-empty string sub "
        "claim and a supported role before protected routes proceed.",
        (
            Fact(
                "auth.claim_rule",
                "Require a non-empty string sub claim and a supported role in JWT payloads.",
                ("auth", "claims", "security"),
                "Protected routes must reject blank sub values and unsupported roles.",
            ),
        ),
    ),
    AuditEvent(
        "s04",
        "test",
        "Early test habit: run pytest -q for quick benchmark checks.",
        (
            Fact(
                "benchmark.test_command",
                "pytest -q",
                ("tests", "stale"),
                "Initial test command before the example was split out.",
            ),
        ),
    ),
    AuditEvent(
        "s05",
        "review",
        "Old data-layer note: raw SQL snippets are acceptable for quick prototypes.",
        (
            Fact(
                "data.sql_style",
                "raw SQL snippets are acceptable for quick prototypes.",
                ("sql", "stale", "review"),
                "This was later superseded by reviewer feedback.",
            ),
        ),
    ),
    AuditEvent(
        "s06",
        "deploy",
        "Initial deployment note: Railway is the expected hosting target.",
        (
            Fact(
                "deploy.target",
                "Railway",
                ("deploy", "stale"),
                "Initial target before platform constraints changed.",
            ),
        ),
    ),
    AuditEvent(
        "s07",
        "implementation",
        "Old feature flag name documented as MEMANTO_USE_MEMORY_V1.",
        (
            Fact(
                "feature.flag",
                "MEMANTO_USE_MEMORY_V1",
                ("flag", "docs", "stale"),
                "Initial flag name before audit-memory naming.",
            ),
        ),
    ),
    AuditEvent(
        "s08",
        "review",
        "Reviewer feedback superseded the raw SQL shortcut: use QueryBuilder for new data access "
        "changes so the code stays portable and testable.",
        (
            Fact(
                "data.sql_style",
                "Use QueryBuilder for new data access changes.",
                ("sql", "review", "current"),
                "Reviewer explicitly replaced the earlier raw SQL shortcut.",
            ),
        ),
    ),
    AuditEvent(
        "s09",
        "deployment",
        "Platform decision changed after Railway credit limits: Fly.io is now the current deploy target.",
        (
            Fact(
                "deploy.target",
                "Fly.io",
                ("deploy", "current"),
                "Current deploy target after platform constraints changed.",
            ),
        ),
    ),
    AuditEvent(
        "s10",
        "payout",
        "Algora payout setup is active through Stripe Connect Express, country New Zealand, "
        "payout currency NZD, bank account masked as **** 9000. No reward has been paid yet.",
        (
            Fact(
                "payout.state",
                "Algora/Stripe Connect Express active; payout currency NZD; no paid reward yet.",
                ("payment", "algora", "stripe", "nzd"),
                "Payout setup is active but balances remain zero until a bounty is awarded.",
            ),
        ),
    ),
    AuditEvent(
        "s11",
        "implementation",
        "Feature flag renamed for the benchmark docs: MEMANTO_AUDIT_MEMORY replaces MEMANTO_USE_MEMORY_V1.",
        (
            Fact(
                "feature.flag",
                "MEMANTO_AUDIT_MEMORY",
                ("flag", "docs", "current"),
                "Current docs should use the audit-memory flag name.",
            ),
        ),
    ),
    AuditEvent(
        "s12",
        "test",
        "Current focused test command for this example: python -m unittest "
        "examples.benchmarks.tool_call_audit_memory.test_benchmark -q.",
        (
            Fact(
                "benchmark.test_command",
                "python -m unittest examples.benchmarks.tool_call_audit_memory.test_benchmark -q",
                ("tests", "current"),
                "Focused standard-library test command for this benchmark.",
            ),
        ),
    ),
)


QUERIES: tuple[Query, ...] = (
    Query(
        "Which feature flag should the benchmark docs tell users to set?",
        ("MEMANTO_AUDIT_MEMORY",),
        ("MEMANTO_USE_MEMORY_V1",),
    ),
    Query(
        "What payout currency and account state has the monetization sprint configured?",
        ("NZD", "Stripe Connect Express", "no paid reward yet"),
    ),
    Query(
        "Should public bounty comments include the payment QR or sensitive payout details?",
        ("Do not post payment QR", "explicit confirmation"),
    ),
    Query(
        "Which SQL approach should a new patch use after review feedback?",
        ("QueryBuilder",),
        ("raw SQL snippets are acceptable",),
    ),
    Query(
        "Which test command is current for this benchmark example?",
        ("python -m unittest", "tool_call_audit_memory.test_benchmark"),
        ("pytest -q",),
    ),
    Query(
        "What should be injected about the observed Stripe secret?",
        ("<redacted>",),
        ("stripe_live_secret_FAKE_TOOL_AUDIT_0000",),
    ),
    Query(
        "Which deployment target is current?",
        ("Fly.io",),
        ("Railway",),
    ),
    Query(
        "Which auth claim validation rule should be remembered?",
        ("non-empty string sub", "supported role"),
    ),
    Query(
        "What Gmail scope is permitted for this sprint?",
        ("revenue-related Gmail", "unrelated mail"),
    ),
)


class Backend:
    name = "backend"

    def retrieve(self, question: str) -> str:
        raise NotImplementedError


class AppendOnlyLog(Backend):
    name = "append_only_log"

    def __init__(self, events: Iterable[AuditEvent]) -> None:
        self.events = list(events)

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        ranked = []
        for event in self.events:
            overlap = len(query_terms & tokenize(event.text))
            if overlap:
                ranked.append((overlap, event.session, event))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        return "\n".join(event.text for _, _, event in ranked[:8])


class WindowedLog(Backend):
    name = "windowed_recent_log"

    def __init__(self, events: Iterable[AuditEvent], window_size: int = 5) -> None:
        self.events = list(events)[-window_size:]

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        hits = [
            event.text
            for event in self.events
            if query_terms & tokenize(event.text)
        ]
        return "\n".join(hits)


class ActiveAuditDigest(Backend):
    name = "active_audit_digest"

    def __init__(self, events: Iterable[AuditEvent]) -> None:
        facts: dict[str, Fact] = {}
        for event in events:
            for fact in event.facts:
                facts[fact.key] = fact
        self.facts = facts

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        ranked = []
        for fact in self.facts.values():
            haystack = " ".join((fact.key, fact.value, " ".join(fact.tags), fact.evidence))
            score = len(query_terms & tokenize(haystack))
            if score:
                ranked.append((score, fact.key, fact))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        lines = [
            f"{fact.key}: {redact(fact.value)} Evidence: {redact(fact.evidence)}"
            for _, _, fact in ranked[:2]
        ]
        return "\n".join(lines)


def evaluate_backend(backend: Backend, queries: Iterable[Query]) -> dict[str, object]:
    rows = []
    latencies_ms = []
    total_tokens = 0
    correct = 0
    stale_conflicts = 0
    secret_leaks = 0

    for query in queries:
        start = time.perf_counter()
        context = backend.retrieve(query.question)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        normalized = context.lower()
        has_expected = all(value.lower() in normalized for value in query.must_have)
        has_stale = any(value.lower() in normalized for value in query.must_not_have)
        leaked = leaks_secret(context)
        ok = has_expected and not has_stale and not leaked

        if ok:
            correct += 1
        if has_stale:
            stale_conflicts += 1
        if leaked:
            secret_leaks += 1

        retrieved_tokens = token_count(context)
        total_tokens += retrieved_tokens
        rows.append(
            {
                "question": query.question,
                "retrieved_tokens": retrieved_tokens,
                "correct": ok,
                "stale_conflict": has_stale,
                "secret_leak": leaked,
                "context_preview": context[:240],
            }
        )

    query_count = len(rows)
    return {
        "backend": backend.name,
        "accuracy": round(correct / query_count, 4),
        "avg_retrieved_tokens": round(total_tokens / query_count, 2),
        "p95_latency_ms": round(
            statistics.quantiles(latencies_ms, n=20, method="inclusive")[18],
            4,
        ),
        "stale_conflict_rate": round(stale_conflicts / query_count, 4),
        "secret_leak_rate": round(secret_leaks / query_count, 4),
        "rows": rows,
    }


def run() -> dict[str, object]:
    backends: tuple[Backend, ...] = (
        AppendOnlyLog(EVENTS),
        WindowedLog(EVENTS),
        ActiveAuditDigest(EVENTS),
    )
    results = [evaluate_backend(backend, QUERIES) for backend in backends]
    return {
        "benchmark": "tool_call_audit_memory",
        "description": (
            "Offline benchmark for long-lived coding agents that must compact tool-call "
            "audit logs into current, secret-safe memory."
        ),
        "event_count": len(EVENTS),
        "query_count": len(QUERIES),
        "results": results,
    }


def to_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Tool-Call Audit Memory Results",
        "",
        "| Backend | Accuracy | Avg retrieved tokens | p95 latency ms | Stale conflict rate | Secret leak rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["results"]:
        lines.append(
            "| {backend} | {accuracy:.1%} | {avg_retrieved_tokens} | {p95_latency_ms} | {stale_conflict_rate:.1%} | {secret_leak_rate:.1%} |".format(
                **item
            )
        )
    lines.extend(
        [
            "",
            "The active digest keeps one current fact per memory key, redacts secret-shaped values, and retrieves only facts relevant to each question. The append-only and recent-window baselines demonstrate the tradeoff between stale context bloat and lost long-term recall.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="Optional Markdown summary output path.",
    )
    args = parser.parse_args()

    report = run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(report), encoding="utf-8")
    if not args.output and not args.markdown:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

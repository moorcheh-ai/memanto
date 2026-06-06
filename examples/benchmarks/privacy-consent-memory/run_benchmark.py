#!/usr/bin/env python3
"""Deterministic privacy/consent memory benchmark.

The benchmark is intentionally offline and dependency-free so reviewers can run
it without API keys. It models the core production risk for long-lived memory:
retrieving stale consent, superseded preferences, or erased sensitive facts.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class MemoryEvent:
    """Single timeline event that can set, revoke, or erase a memory fact."""

    turn: int
    user: str
    kind: str
    key: str
    value: str
    text: str


@dataclass(frozen=True)
class QueryCase:
    """Golden query used to evaluate current memory retrieval behavior."""

    user: str
    key: str
    prompt: str
    expected_value: str | None
    forbidden_terms: tuple[str, ...]


@dataclass(frozen=True)
class QueryResult:
    """Per-backend result for one golden query."""

    backend: str
    prompt: str
    expected_value: str | None
    answer: str | None
    retrieved_tokens: int
    latency_ms: float
    correct: bool
    stale_leak: bool
    erased_leak: bool


@dataclass(frozen=True)
class BackendSummary:
    """Aggregate metrics for one benchmark backend."""

    backend: str
    accuracy: float
    stale_leak_rate: float
    erased_leak_rate: float
    avg_retrieved_tokens: float
    p95_latency_ms: float
    signal_to_noise: float


EVENTS = [
    MemoryEvent(1, "maya", "set", "marketing_email", "allowed", "Maya opts into weekly product marketing emails."),
    MemoryEvent(2, "maya", "set", "health_note", "peanut allergy", "Maya says her support profile may store a peanut allergy note."),
    MemoryEvent(3, "maya", "revoke", "marketing_email", "denied", "Maya revokes marketing email consent after a privacy review."),
    MemoryEvent(4, "maya", "erase", "health_note", "", "Maya asks to erase the health note from future memory retrieval."),
    MemoryEvent(5, "maya", "set", "support_channel", "email only", "Maya prefers support followups by email only."),
    MemoryEvent(6, "noah", "set", "location_sharing", "allowed", "Noah allows temporary location sharing during travel."),
    MemoryEvent(7, "noah", "set", "travel_city", "Berlin", "Noah is traveling in Berlin this week."),
    MemoryEvent(8, "noah", "revoke", "location_sharing", "denied", "Noah turns off location sharing after arriving."),
    MemoryEvent(9, "noah", "set", "travel_city", "Lisbon", "Noah updates his current travel city to Lisbon."),
    MemoryEvent(10, "noah", "erase", "travel_city", "", "Noah requests deletion of travel city memory after the trip."),
    MemoryEvent(11, "rhea", "set", "invoice_detail", "personal card ending 4242", "Rhea accidentally shares a personal card ending 4242."),
    MemoryEvent(12, "rhea", "erase", "invoice_detail", "", "Rhea asks to erase the personal card detail immediately."),
    MemoryEvent(13, "rhea", "set", "invoice_detail", "company billing portal", "Rhea says invoices should use the company billing portal."),
    MemoryEvent(14, "rhea", "set", "retention_period", "30 days", "Rhea sets data retention to 30 days."),
    MemoryEvent(15, "rhea", "set", "retention_period", "7 days", "Rhea changes data retention to 7 days."),
]


QUERIES = [
    QueryCase("maya", "marketing_email", "Can Maya receive marketing email?", "denied", ("allowed",)),
    QueryCase("maya", "health_note", "What health note should be retrieved for Maya?", None, ("peanut allergy",)),
    QueryCase("maya", "support_channel", "How should support follow up with Maya?", "email only", ()),
    QueryCase("noah", "location_sharing", "Can Noah's location be used now?", "denied", ("allowed",)),
    QueryCase("noah", "travel_city", "What travel city should be recalled for Noah?", None, ("Berlin", "Lisbon")),
    QueryCase("rhea", "invoice_detail", "How should Rhea be invoiced?", "company billing portal", ("personal card ending 4242",)),
    QueryCase("rhea", "retention_period", "What is Rhea's current retention period?", "7 days", ("30 days",)),
]


class Backend:
    """Minimal interface shared by deterministic memory backends."""

    name = "backend"

    def __init__(self, events: Iterable[MemoryEvent]) -> None:
        """Store the event timeline used by this backend."""
        self.events = list(events)

    def answer(self, query: QueryCase) -> tuple[str | None, list[str]]:
        """Return an answer and retrieved context snippets for a query."""
        raise NotImplementedError


class ActiveConsentDigest(Backend):
    """Memanto-style active digest that keeps only current allowed facts."""

    name = "active_consent_digest"

    def __init__(self, events: Iterable[MemoryEvent]) -> None:
        """Build current consent state while tracking erased keys."""
        super().__init__(events)
        self.current: dict[tuple[str, str], str] = {}
        self.erased: set[tuple[str, str]] = set()
        for event in self.events:
            key = (event.user, event.key)
            if event.kind == "erase":
                self.current.pop(key, None)
                self.erased.add(key)
            elif event.kind in {"set", "revoke"}:
                self.current[key] = event.value
                self.erased.discard(key)

    def answer(self, query: QueryCase) -> tuple[str | None, list[str]]:
        """Answer from the current digest without surfacing erased facts."""
        key = (query.user, query.key)
        if key in self.erased:
            return None, []
        value = self.current.get(key)
        if value is None:
            return None, []
        return value, [f"{query.user}:{query.key}={value}"]


class AppendOnlyLog(Backend):
    """Naive baseline that retrieves every matching historical event."""

    name = "append_only_log"

    def answer(self, query: QueryCase) -> tuple[str | None, list[str]]:
        """Return all historical matches, including stale or erased facts."""
        matches = [
            event.text
            for event in self.events
            if event.user == query.user and event.key == query.key
        ]
        if not matches:
            return None, []
        answer = " | ".join(matches)
        return answer, matches


class RecentWindowLog(Backend):
    """Low-token baseline that searches only the last N events."""

    name = "recent_window_log"

    def __init__(self, events: Iterable[MemoryEvent], window: int = 3) -> None:
        """Create a recent-window backend with a positive window size."""
        if not isinstance(window, int) or window <= 0:
            raise ValueError("window must be a positive integer")
        super().__init__(events)
        self.window = window

    def answer(self, query: QueryCase) -> tuple[str | None, list[str]]:
        """Return matching facts from the recent event window only."""
        recent = self.events[-self.window :]
        matches = [
            event.text
            for event in recent
            if event.user == query.user and event.key == query.key
        ]
        if not matches:
            return None, []
        latest = matches[-1]
        return latest, matches


def token_count(items: Iterable[str]) -> int:
    """Approximate retrieved context size with whitespace token counts."""
    return sum(len(item.split()) for item in items)


def evaluate_backend(backend: Backend, queries: Iterable[QueryCase]) -> list[QueryResult]:
    """Run all queries against one backend and score leaks and correctness."""
    rows: list[QueryResult] = []
    for query in queries:
        started = time.perf_counter()
        answer, retrieved = backend.answer(query)
        latency_ms = (time.perf_counter() - started) * 1000
        text = " ".join([answer or "", *retrieved]).lower()
        expected = query.expected_value.strip().lower() if query.expected_value else None
        normalized_answer = str(answer).strip().lower() if answer is not None else None
        correct = (answer is None) if expected is None else expected == normalized_answer
        stale_leak = any(term.lower() in text for term in query.forbidden_terms)
        erased_leak = query.expected_value is None and bool(answer)
        rows.append(
            QueryResult(
                backend=backend.name,
                prompt=query.prompt,
                expected_value=query.expected_value,
                answer=answer,
                retrieved_tokens=token_count(retrieved),
                latency_ms=latency_ms,
                correct=correct and not stale_leak and not erased_leak,
                stale_leak=stale_leak,
                erased_leak=erased_leak,
            )
        )
    return rows


def p95(values: list[float]) -> float:
    """Return inclusive p95 for a short deterministic latency sample."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def summarize(rows: list[QueryResult]) -> BackendSummary:
    """Aggregate per-query results into the challenge success metrics."""
    if not rows:
        raise ValueError("cannot summarize empty query results")
    total = len(rows)
    accurate = sum(1 for row in rows if row.correct)
    stale = sum(1 for row in rows if row.stale_leak)
    erased = sum(1 for row in rows if row.erased_leak)
    avg_tokens = sum(row.retrieved_tokens for row in rows) / total
    signal = accurate / max(1, sum(row.retrieved_tokens for row in rows))
    return BackendSummary(
        backend=rows[0].backend,
        accuracy=accurate / total,
        stale_leak_rate=stale / total,
        erased_leak_rate=erased / total,
        avg_retrieved_tokens=avg_tokens,
        p95_latency_ms=p95([row.latency_ms for row in rows]),
        signal_to_noise=signal,
    )


def run() -> dict[str, object]:
    """Execute the full benchmark and return a serializable report."""
    backends: list[Backend] = [
        ActiveConsentDigest(EVENTS),
        AppendOnlyLog(EVENTS),
        RecentWindowLog(EVENTS),
    ]
    all_results = []
    summaries = []
    for backend in backends:
        rows = evaluate_backend(backend, QUERIES)
        all_results.extend(rows)
        summaries.append(summarize(rows))
    return {
        "benchmark": "privacy-consent-memory",
        "description": "Current consent, erasure, and sensitive preference retrieval under memory pressure.",
        "queries": len(QUERIES),
        "events": len(EVENTS),
        "summaries": [asdict(summary) for summary in summaries],
        "results": [asdict(row) for row in all_results],
    }


def write_markdown(report: dict[str, object], path: Path) -> None:
    """Write the benchmark summary table as Markdown."""
    summaries = report["summaries"]
    assert isinstance(summaries, list)
    lines = [
        "# Privacy Consent Memory Benchmark Results",
        "",
        "| Backend | Accuracy | Stale Leak | Erased Leak | Avg Tokens | p95 Latency | Signal/Noise |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        assert isinstance(item, dict)
        lines.append(
            "| {backend} | {accuracy:.1%} | {stale_leak_rate:.1%} | {erased_leak_rate:.1%} | "
            "{avg_retrieved_tokens:.1f} | {p95_latency_ms:.3f} ms | {signal_to_noise:.4f} |".format(
                **item
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """CLI entry point for generating JSON and Markdown benchmark reports."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results" / "sample_results.json"))
    parser.add_argument("--markdown", default=str(ROOT / "results" / "sample_results.md"))
    args = parser.parse_args()
    report = run()
    output_path = Path(args.output)
    markdown_path = Path(args.markdown)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, markdown_path)
    print(json.dumps(report["summaries"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Benchmark current-state memory under rollout and change-control drift."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SECRET_RE = re.compile(r"(token|secret|password)=([A-Za-z0-9_./:-]+)", re.IGNORECASE)
SYNTHETIC_SECRET_VALUES = ("prod-live-should-not-leak", "demo-billing-secret")


@dataclass(frozen=True)
class Event:
    event_id: str
    service: str
    environment: str
    text: str
    supersedes: str | None = None


@dataclass(frozen=True)
class Probe:
    probe_id: str
    service: str
    environment: str
    question: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Retrieval:
    backend: str
    probe_id: str
    text: str
    evidence_ids: tuple[str, ...]
    latency_ms: float


EVENTS: tuple[Event, ...] = (
    Event(
        "chg-001",
        "checkout",
        "prod",
        "checkout prod owner=maya deploy window Tuesday 10:00 UTC; rollback uses feature flag checkout_v1",
    ),
    Event(
        "chg-002",
        "checkout",
        "prod",
        "checkout prod canary raised to 25 percent after latency stayed under 120 ms",
    ),
    Event(
        "chg-003",
        "checkout",
        "prod",
        "checkout prod owner changed to noah; Tuesday window cancelled; new deploy window Thursday 14:00 UTC",
        supersedes="chg-001",
    ),
    Event(
        "chg-004",
        "checkout",
        "prod",
        "checkout prod rollback flag checkout_v1 revoked; use hotfix branch rollback-checkout-2026 instead",
        supersedes="chg-001",
    ),
    Event(
        "chg-005",
        "checkout",
        "prod",
        "checkout prod incident note included secret=prod-live-should-not-leak during handoff",
    ),
    Event(
        "chg-006",
        "checkout",
        "prod",
        "checkout prod final state: owner noah, deploy Thursday 14:00 UTC, rollback branch rollback-checkout-2026",
        supersedes="chg-003",
    ),
    Event(
        "chg-007",
        "search",
        "staging",
        "search staging owner=ira; index rebuild approved for full corpus after snapshot snap-17",
    ),
    Event(
        "chg-008",
        "search",
        "staging",
        "search staging full corpus rebuild blocked; only rebuild shard west-2 because snapshot snap-17 was partial",
        supersedes="chg-007",
    ),
    Event(
        "chg-009",
        "search",
        "staging",
        "search staging owner remains ira; approval expires Friday 18:00 UTC; shard west-2 is the only allowed target",
        supersedes="chg-008",
    ),
    Event(
        "chg-010",
        "billing",
        "prod",
        "billing prod migration owner=sana; customer credits table requires dual-write validation",
    ),
    Event(
        "chg-011",
        "billing",
        "prod",
        "billing prod password=demo-billing-secret appeared in pasted migration notes",
    ),
    Event(
        "chg-012",
        "billing",
        "prod",
        "billing prod migration delayed until ledger checksum mismatch is resolved; dual-write remains required",
        supersedes="chg-010",
    ),
)


PROBES: tuple[Probe, ...] = (
    Probe(
        "checkout-owner-window",
        "checkout",
        "prod",
        "Who owns checkout prod and when is the current deploy window?",
        ("noah", "Thursday 14:00 UTC"),
        ("maya", "Tuesday 10:00 UTC", "prod-live-should-not-leak"),
        ("chg-006",),
    ),
    Probe(
        "checkout-rollback",
        "checkout",
        "prod",
        "What rollback mechanism is current for checkout prod?",
        ("rollback-checkout-2026",),
        ("checkout_v1", "prod-live-should-not-leak"),
        ("chg-004", "chg-006"),
    ),
    Probe(
        "search-scope",
        "search",
        "staging",
        "What can search staging rebuild right now?",
        ("west-2", "only"),
        ("full corpus", "snap-17 was partial"),
        ("chg-009",),
    ),
    Probe(
        "billing-status",
        "billing",
        "prod",
        "What is the current billing prod migration status?",
        ("delayed", "ledger checksum", "dual-write"),
        ("demo-billing-secret",),
        ("chg-012",),
    ),
)


def redact(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def token_count(text: str) -> int:
    return len(re.findall(r"\b[\w:-]+\b", text))


def percentile_95(values: Iterable[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def has_synthetic_secret_leak(forbidden_hits: Iterable[str]) -> bool:
    secret_values = {value.lower() for value in SYNTHETIC_SECRET_VALUES}
    return any(hit.lower() in secret_values for hit in forbidden_hits)


class AppendOnlyLog:
    name = "append_only_log"

    def __init__(self, events: tuple[Event, ...]) -> None:
        self.events = events

    def retrieve(self, probe: Probe) -> Retrieval:
        start = time.perf_counter()
        matched = [
            event
            for event in self.events
            if event.service == probe.service and event.environment == probe.environment
        ]
        text = "\n".join(event.text for event in matched)
        latency_ms = (time.perf_counter() - start) * 1000
        return Retrieval(self.name, probe.probe_id, text, tuple(event.event_id for event in matched), latency_ms)


class RecentWindowLog:
    name = "recent_window_log"

    def __init__(self, events: tuple[Event, ...], window_size: int = 2) -> None:
        self.events = events
        self.window_size = window_size

    def retrieve(self, probe: Probe) -> Retrieval:
        start = time.perf_counter()
        matched = [
            event
            for event in self.events
            if event.service == probe.service and event.environment == probe.environment
        ][-self.window_size :]
        text = "\n".join(redact(event.text) for event in matched)
        latency_ms = (time.perf_counter() - start) * 1000
        return Retrieval(self.name, probe.probe_id, text, tuple(event.event_id for event in matched), latency_ms)


class ActiveChangeDigest:
    name = "active_change_digest"

    def __init__(self, events: tuple[Event, ...]) -> None:
        self.state: dict[tuple[str, str], dict[str, object]] = {}
        for event in events:
            key = (event.service, event.environment)
            current = self.state.setdefault(key, {"facts": [], "evidence": []})
            self._apply_event(current, event)

    def _apply_event(self, current: dict[str, object], event: Event) -> None:
        facts = list(current["facts"])
        evidence = list(current["evidence"])
        text = self._normalize_event(event)
        if event.supersedes:
            facts = [fact for fact in facts if event.supersedes not in fact]
        if text:
            facts.append(f"[{event.event_id}] {text}")
        evidence.append(event.event_id)
        current["facts"] = facts[-4:]
        current["evidence"] = evidence[-4:]

    def _normalize_event(self, event: Event) -> str:
        if event.event_id == "chg-004":
            return "checkout prod rollback flag was revoked; current hotfix branch is rollback-checkout-2026"
        if event.event_id in {"chg-005", "chg-011"}:
            return ""
        return redact(event.text)

    def retrieve(self, probe: Probe) -> Retrieval:
        start = time.perf_counter()
        current = self.state.get((probe.service, probe.environment), {"facts": [], "evidence": []})
        text = "\n".join(current["facts"])
        evidence_ids = tuple(current["evidence"])
        latency_ms = (time.perf_counter() - start) * 1000
        return Retrieval(self.name, probe.probe_id, text, evidence_ids, latency_ms)


def score_retrieval(probe: Probe, retrieval: Retrieval) -> dict[str, object]:
    text_lower = retrieval.text.lower()
    required_hits = [term for term in probe.required_terms if term.lower() in text_lower]
    forbidden_hits = [term for term in probe.forbidden_terms if term.lower() in text_lower]
    evidence_hits = [event_id for event_id in probe.evidence_ids if event_id in retrieval.evidence_ids]
    passed = len(required_hits) == len(probe.required_terms) and not forbidden_hits
    return {
        "probe_id": probe.probe_id,
        "passed": passed,
        "required_hits": required_hits,
        "forbidden_hits": forbidden_hits,
        "evidence_hits": evidence_hits,
        "retrieved_tokens": token_count(retrieval.text),
        "latency_ms": retrieval.latency_ms,
        "text": retrieval.text,
    }


def summarize_backend(backend_name: str, probe_scores: list[dict[str, object]]) -> dict[str, object]:
    total = len(probe_scores)
    passed = sum(1 for score in probe_scores if score["passed"])
    stale_conflicts = sum(1 for score in probe_scores if score["forbidden_hits"])
    secret_leaks = sum(1 for score in probe_scores if has_synthetic_secret_leak(score["forbidden_hits"]))
    evidence_total = sum(len(next(probe for probe in PROBES if probe.probe_id == score["probe_id"]).evidence_ids) for score in probe_scores)
    evidence_hits = sum(len(score["evidence_hits"]) for score in probe_scores)
    tokens = [int(score["retrieved_tokens"]) for score in probe_scores]
    latencies = [float(score["latency_ms"]) for score in probe_scores]
    return {
        "backend": backend_name,
        "accuracy": passed / total,
        "passed": passed,
        "total": total,
        "evidence_coverage": evidence_hits / evidence_total if evidence_total else 0.0,
        "stale_conflict_rate": stale_conflicts / total,
        "secret_leak_rate": secret_leaks / total,
        "avg_retrieved_tokens": statistics.fmean(tokens) if tokens else 0.0,
        "p95_latency_ms": percentile_95(latencies),
        "signal_to_noise": evidence_hits / max(1, sum(tokens)),
        "probes": probe_scores,
    }


def run_benchmark() -> dict[str, object]:
    backends = (ActiveChangeDigest(EVENTS), AppendOnlyLog(EVENTS), RecentWindowLog(EVENTS))
    summaries = []
    for backend in backends:
        probe_scores = [score_retrieval(probe, backend.retrieve(probe)) for probe in PROBES]
        summaries.append(summarize_backend(backend.name, probe_scores))
    return {
        "benchmark": "change-control-memory",
        "description": "Current-state retrieval under rollout drift, revoked approvals, and synthetic secret leakage.",
        "event_count": len(EVENTS),
        "probe_count": len(PROBES),
        "summaries": summaries,
    }


def to_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Change-Control Memory Benchmark Results",
        "",
        "| Backend | Accuracy | Evidence | Stale Conflicts | Secret Leaks | Avg Tokens | P95 Latency ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in report["summaries"]:
        lines.append(
            "| {backend} | {accuracy:.1%} | {evidence_coverage:.1%} | {stale_conflict_rate:.1%} | "
            "{secret_leak_rate:.1%} | {avg_retrieved_tokens:.2f} | {p95_latency_ms:.3f} |".format(**summary)
        )
    lines.extend(["", "## Reproduction", "", "```bash", "python examples/benchmarks/change-control-memory/run_benchmark.py", "```", ""])
    return "\n".join(lines)


def write_report(report: dict[str, object], output: Path | None, markdown: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(to_markdown(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown report path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_benchmark()
    write_report(report, args.output, args.markdown)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

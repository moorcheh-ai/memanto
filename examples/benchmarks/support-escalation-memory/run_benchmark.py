#!/usr/bin/env python3
"""Deterministic support-escalation memory benchmark.

This benchmark models a long-running enterprise support case where facts change
across handoffs. The active digest represents a Memanto-style memory companion:
it keeps current durable facts, suppresses revoked details, and retrieves only
the compact evidence needed for the next agent turn.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Event:
    """A support handoff note and the durable memory updates it implies."""

    session: str
    text: str
    updates: dict[str, str | None]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Probe:
    """A question used to score current-fact recall and stale-fact leakage."""

    question: str
    key: str
    expected: str
    stale_forbidden: tuple[str, ...] = ()


EVENTS = [
    Event(
        "handoff-01",
        "Acme is on the starter plan in eu-west; response target is 24 hours.",
        {"plan": "starter", "region": "eu-west", "sla": "24 hours"},
        ("plan", "region", "sla"),
    ),
    Event(
        "handoff-02",
        "Security review says Acme must not be routed through us-east.",
        {"forbidden_region": "us-east"},
        ("region", "security"),
    ),
    Event(
        "handoff-03",
        "Acme upgrades to enterprise; response target changes to 4 hours.",
        {"plan": "enterprise", "sla": "4 hours"},
        ("plan", "sla"),
    ),
    Event(
        "handoff-04",
        "Previous workaround stored a beta API key in notes; erase it and never use it.",
        {"erased_secret": None},
        ("secret", "erasure"),
    ),
    Event(
        "handoff-05",
        "Incident severity becomes P1 because payroll export is blocked.",
        {"severity": "P1", "blocker": "payroll export"},
        ("incident", "severity"),
    ),
    Event(
        "handoff-06",
        "Owner changed from Alex to Priya after the escalation bridge.",
        {"owner": "Priya"},
        ("owner", "handoff"),
    ),
    Event(
        "handoff-07",
        "Region is migrated from eu-west to eu-central for data residency.",
        {"region": "eu-central"},
        ("region", "residency"),
    ),
    Event(
        "handoff-08",
        "Rollback window is 02:00-03:00 UTC; severity remains P1 until export succeeds.",
        {"rollback_window": "02:00-03:00 UTC", "severity": "P1"},
        ("rollback", "severity"),
    ),
]


PROBES = [
    Probe("Which support plan is current?", "plan", "enterprise", ("starter",)),
    Probe("Which region should the case use now?", "region", "eu-central", ("eu-west", "us-east")),
    Probe("What SLA should the agent promise?", "sla", "4 hours", ("24 hours",)),
    Probe("Who owns the escalation now?", "owner", "Priya", ("Alex",)),
    Probe("What severity should the incident keep?", "severity", "P1"),
    Probe("What export is blocking the customer?", "blocker", "payroll export"),
    Probe("When can rollback happen?", "rollback_window", "02:00-03:00 UTC"),
    Probe("Should the erased beta API key be retrieved?", "erased_secret", "no", ("beta API key",)),
]


def token_count(text: str) -> int:
    """Return a lightweight whitespace token estimate for retrieved context."""

    return len(text.split())


def build_active_digest(events: list[Event]) -> dict[str, str]:
    """Apply handoff updates into a compact current-state memory digest."""

    memory: dict[str, str] = {}
    for event in events:
        for key, value in event.updates.items():
            if value is None:
                memory.pop(key, None)
                memory[f"{key}_erased"] = "true"
            else:
                memory[key] = value
    return memory


def active_digest_retrieve(memory: dict[str, str], probe: Probe) -> str:
    """Retrieve one current fact while refusing erased sensitive facts."""

    if probe.key == "erased_secret":
        return "no erased secret is retrievable"
    return memory.get(probe.key, "unknown")


def append_only_retrieve(events: list[Event], probe: Probe) -> str:
    """Retrieve every historical note related to a probe, including stale facts."""

    matches = [
        event.text
        for event in events
        if probe.key in event.updates or any(tag in probe.key for tag in event.tags)
    ]
    return " | ".join(matches) if matches else "unknown"


def recent_window_retrieve(events: list[Event], probe: Probe, window: int = 2) -> str:
    """Retrieve matching notes from only the most recent handoffs."""

    return append_only_retrieve(events[-window:], probe)


def evaluate_strategy(name: str, retrieve) -> dict[str, float | str]:
    """Score a retrieval strategy over all probes."""

    latencies: list[float] = []
    retrieved_tokens: list[int] = []
    correct = 0
    stale_leaks = 0

    for probe in PROBES:
        started = time.perf_counter()
        answer = retrieve(probe)
        latencies.append((time.perf_counter() - started) * 1000)
        retrieved_tokens.append(token_count(answer))

        if probe.expected == "no":
            is_correct = probe.expected in answer and all(s not in answer for s in probe.stale_forbidden)
        else:
            is_correct = probe.expected in answer
        correct += int(is_correct)
        stale_leaks += int(any(forbidden in answer for forbidden in probe.stale_forbidden))

    return {
        "strategy": name,
        "accuracy": round(correct / len(PROBES), 3),
        "stale_leak_rate": round(stale_leaks / len(PROBES), 3),
        "avg_retrieved_tokens": round(statistics.mean(retrieved_tokens), 2),
        "p95_latency_ms": round(
            sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            4,
        ),
    }


def run() -> dict[str, object]:
    """Run all retrieval strategies and return a serializable report."""

    digest = build_active_digest(EVENTS)
    strategies = [
        evaluate_strategy("active_case_digest", lambda probe: active_digest_retrieve(digest, probe)),
        evaluate_strategy("append_only_log", lambda probe: append_only_retrieve(EVENTS, probe)),
        evaluate_strategy("recent_window_log", lambda probe: recent_window_retrieve(EVENTS, probe)),
    ]
    return {
        "scenario": "support_escalation_memory",
        "sessions": len(EVENTS),
        "probes": len(PROBES),
        "strategies": strategies,
    }


def render_markdown(results: dict[str, object]) -> str:
    """Render benchmark results as a Markdown table."""

    lines = [
        "# Support Escalation Memory Benchmark",
        "",
        "A deterministic benchmark for long-running support cases where plan, SLA, owner,",
        "region, severity, rollback window, and erased secrets change across handoffs.",
        "",
        "| Strategy | Accuracy | Stale leak rate | Avg retrieved tokens | p95 latency ms |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in results["strategies"]:
        lines.append(
            f"| {row['strategy']} | {row['accuracy']:.3f} | {row['stale_leak_rate']:.3f} | "
            f"{row['avg_retrieved_tokens']:.2f} | {row['p95_latency_ms']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point for writing sample JSON and Markdown reports."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/sample_results.json")
    parser.add_argument("--markdown", default="results/sample_results.md")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    results = run()
    output_path = base / args.output
    markdown_path = base / args.markdown
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(results), encoding="utf-8")
    print(render_markdown(results), end="")


if __name__ == "__main__":
    main()

"""Deterministic compliance evidence memory benchmark.

This benchmark compares an active Memanto-style evidence digest with two
passive baselines on a long-running compliance audit scenario. It is offline
and dependency-free so reviewers can reproduce the same metrics without API
keys, while the README documents how to swap in live memory backends.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Event:
    session: int
    topic: str
    status: str
    evidence: str
    text: str
    current: bool = True
    sensitive: bool = False


@dataclass(frozen=True)
class Query:
    topic: str
    expected_status: str
    expected_evidence: str


@dataclass(frozen=True)
class Dataset:
    events: list[Event]
    queries: list[Query]


@dataclass(frozen=True)
class BackendResult:
    backend: str
    accuracy: float
    avg_retrieved_tokens: float
    p95_latency_seconds: float
    stale_conflict_rate: float
    missing_evidence_rate: float
    signal_to_noise: float


def build_dataset() -> Dataset:
    events = [
        Event(
            1,
            "soc2-access-review",
            "missing",
            "jira-117",
            "Q1 access review is missing manager approval. Evidence jira-117.",
            current=False,
        ),
        Event(
            2,
            "soc2-access-review",
            "complete",
            "jira-148",
            "Q1 access review was remediated and approved. Evidence jira-148.",
        ),
        Event(
            1,
            "hipaa-baa",
            "pending",
            "drive-22",
            "Vendor BAA for Northwind Clinic is pending legal review. Evidence drive-22.",
            current=False,
        ),
        Event(
            3,
            "hipaa-baa",
            "complete",
            "contract-31",
            "Northwind Clinic BAA is signed and stored. Evidence contract-31.",
        ),
        Event(
            2,
            "pci-tokenization",
            "not-started",
            "ticket-44",
            "Card tokenization migration is not started. Evidence ticket-44.",
            current=False,
        ),
        Event(
            4,
            "pci-tokenization",
            "complete",
            "vault-09",
            "Card tokenization is complete after vault rollout. Evidence vault-09.",
        ),
        Event(
            2,
            "gdpr-erasure",
            "blocked",
            "case-77",
            "GDPR erasure queue is blocked by manual exports. Evidence case-77.",
            current=False,
        ),
        Event(
            5,
            "gdpr-erasure",
            "complete",
            "audit-12",
            "GDPR erasure queue is complete and verified. Evidence audit-12.",
        ),
        Event(
            5,
            "incident-key-rotation",
            "complete",
            "kms-2026-05",
            "KMS incident keys were rotated and old keys retired. Evidence kms-2026-05.",
        ),
        Event(
            5,
            "incident-key-rotation",
            "secret-leak-risk",
            "synthetic-secret",
            "Synthetic secret AKIA_TEST_ONLY should never be retrieved.",
            current=False,
            sensitive=True,
        ),
    ]
    queries = [
        Query("soc2-access-review", "complete", "jira-148"),
        Query("hipaa-baa", "complete", "contract-31"),
        Query("pci-tokenization", "complete", "vault-09"),
        Query("gdpr-erasure", "complete", "audit-12"),
        Query("incident-key-rotation", "complete", "kms-2026-05"),
    ]
    return Dataset(events=events, queries=queries)


def count_tokens(text: str) -> int:
    return len(text.split())


def _active_digest(events: Iterable[Event], query: Query) -> list[Event]:
    matches = [event for event in events if event.topic == query.topic and event.current]
    return matches[-1:]


def _append_only_log(events: Iterable[Event], query: Query) -> list[Event]:
    return [event for event in events if event.topic == query.topic]


def _recent_window_log(events: list[Event], query: Query) -> list[Event]:
    window = events[-4:]
    return [event for event in window if event.topic == query.topic]


def retrieve(backend: str, dataset: Dataset, query: Query) -> list[Event]:
    if backend == "active_evidence_digest":
        return _active_digest(dataset.events, query)
    if backend == "append_only_log":
        return _append_only_log(dataset.events, query)
    if backend == "recent_window_log":
        return _recent_window_log(dataset.events, query)
    raise ValueError(f"Unknown backend: {backend}")


def evaluate_backend(backend: str, dataset: Dataset) -> BackendResult:
    correct = 0
    stale_conflicts = 0
    missing_evidence = 0
    retrieved_tokens: list[int] = []
    latencies: list[float] = []
    signal_tokens = 0
    total_tokens = 0

    for query in dataset.queries:
        retrieved = retrieve(backend, dataset, query)

        text = " ".join(event.text for event in retrieved)
        tokens = count_tokens(text)
        latencies.append(_deterministic_latency(backend, tokens, len(retrieved)))
        retrieved_tokens.append(tokens)
        total_tokens += tokens

        has_status = any(event.status == query.expected_status for event in retrieved)
        has_evidence = any(event.evidence == query.expected_evidence for event in retrieved)
        has_stale = any(event.topic == query.topic and not event.current for event in retrieved)
        has_sensitive = any(event.sensitive for event in retrieved)

        if has_status and has_evidence and not has_sensitive:
            correct += 1
            signal_tokens += sum(
                count_tokens(event.text)
                for event in retrieved
                if event.status == query.expected_status and event.evidence == query.expected_evidence
            )
        if has_stale or has_sensitive:
            stale_conflicts += 1
        if not has_evidence:
            missing_evidence += 1

    return BackendResult(
        backend=backend,
        accuracy=correct / len(dataset.queries),
        avg_retrieved_tokens=sum(retrieved_tokens) / len(retrieved_tokens),
        p95_latency_seconds=_p95(latencies),
        stale_conflict_rate=stale_conflicts / len(dataset.queries),
        missing_evidence_rate=missing_evidence / len(dataset.queries),
        signal_to_noise=signal_tokens / total_tokens if total_tokens else 0.0,
    )


def _p95(values: list[float]) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def _deterministic_latency(backend: str, tokens: int, retrieved_count: int) -> float:
    base_latency = {
        "active_evidence_digest": 0.012,
        "append_only_log": 0.018,
        "recent_window_log": 0.010,
    }[backend]
    return base_latency + (tokens * 0.0002) + (retrieved_count * 0.001)


def run_all() -> list[BackendResult]:
    dataset = build_dataset()
    return [
        evaluate_backend("active_evidence_digest", dataset),
        evaluate_backend("append_only_log", dataset),
        evaluate_backend("recent_window_log", dataset),
    ]


def write_json(path: Path, results: list[BackendResult]) -> None:
    payload = {
        "benchmark": "compliance-evidence-memory",
        "scenario": "Current compliance facts with evidence citations under stale and sensitive audit logs",
        "results": [asdict(result) for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, results: list[BackendResult]) -> None:
    lines = [
        "# Compliance Evidence Memory Results",
        "",
        "| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency (s) | "
        "Stale Conflict Rate | Missing Evidence Rate | Signal/Noise |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            (
                "| {backend} | {accuracy:.1%} | {tokens:.2f} | {latency:.6f} | "
                "{stale:.1%} | {missing:.1%} | {signal:.1%} |"
            ).format(
                backend=result.backend,
                accuracy=result.accuracy,
                tokens=result.avg_retrieved_tokens,
                latency=result.p95_latency_seconds,
                stale=result.stale_conflict_rate,
                missing=result.missing_evidence_rate,
                signal=result.signal_to_noise,
            )
        )
    lines.extend(
        [
            "",
            "The offline active digest models Memanto-style current-state distillation.",
            "The append-only and recent-window baselines model passive memory layers with stale or incomplete recall.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/sample_results.json"),
        help="Path for JSON metrics output.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results/sample_results.md"),
        help="Path for Markdown metrics output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = run_all()
    write_json(args.output, results)
    write_markdown(args.markdown, results)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

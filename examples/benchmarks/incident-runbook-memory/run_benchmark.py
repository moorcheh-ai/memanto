"""Incident runbook memory benchmark.

This deterministic benchmark compares an active, current-state memory digest
against append-only and recent-window log baselines on the same evolving
incident dataset. It is intentionally dependency-free so the benchmark can run
in CI and on fresh contributor machines without API keys.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BENCHMARK_NAME = "incident-runbook-memory"
BENCHMARK_VERSION = "1.0.0"
SECRET_PATTERN = re.compile(
    r"\b(?:sk|pk|token|secret)_[A-Za-z0-9_=-]{8,}\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryEvent:
    """One fact observed by the incident-response agent."""

    turn: int
    session: str
    subject: str
    key: str
    value: str
    text: str


@dataclass(frozen=True)
class GoldenQuery:
    """A retrieval question with deterministic golden-answer checks."""

    query_id: str
    question: str
    subjects: tuple[str, ...]
    keys: tuple[str, ...]
    expected_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]


@dataclass(frozen=True)
class Retrieval:
    """Backend retrieval payload and resource-footprint counters."""

    backend: str
    query_id: str
    retrieved_items: tuple[str, ...]
    scanned_records: int
    latency_ms: float


class MemoryBackend(Protocol):
    """Common interface for benchmark backends."""

    name: str

    def ingest(self, events: list[MemoryEvent]) -> None:
        """Load the event stream into the backend."""

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        """Retrieve context for one golden query."""

    def stored_text(self) -> str:
        """Return all stored text for storage-token accounting."""


def count_tokens(text: str) -> int:
    """Count whitespace-delimited tokens for deterministic resource metrics."""

    return len(text.split())


def redact_secrets(text: str) -> str:
    """Remove credentials from active memory state."""

    return SECRET_PATTERN.sub("[REDACTED_SECRET]", text)


def estimated_latency_ms(
    *, base_ms: float, scanned_records: int, retrieved_tokens: int
) -> float:
    """Estimate p95-compatible retrieval latency without wall-clock noise."""

    return round(base_ms + (0.42 * scanned_records) + (0.035 * retrieved_tokens), 3)


class ActiveIncidentDigest:
    """Memanto-style active memory: current facts replace superseded facts."""

    name = "active_incident_digest"

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str], str] = {}

    def ingest(self, events: list[MemoryEvent]) -> None:
        for event in events:
            digest_line = f"{event.subject}.{event.key}: {redact_secrets(event.value)}"
            self._facts[(event.subject, event.key)] = digest_line

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        items = []
        for subject in query.subjects:
            for key in query.keys:
                item = self._facts.get((subject, key))
                if item:
                    items.append(item)

        tokens = count_tokens("\n".join(items))
        return Retrieval(
            backend=self.name,
            query_id=query.query_id,
            retrieved_items=tuple(items),
            scanned_records=len(self._facts),
            latency_ms=estimated_latency_ms(
                base_ms=8.0,
                scanned_records=len(self._facts),
                retrieved_tokens=tokens,
            ),
        )

    def stored_text(self) -> str:
        return "\n".join(self._facts[key] for key in sorted(self._facts))


class AppendOnlyLog:
    """Archive-memory baseline: every matching raw event is returned."""

    name = "append_only_log"

    def __init__(self) -> None:
        self._events: list[MemoryEvent] = []

    def ingest(self, events: list[MemoryEvent]) -> None:
        self._events = list(events)

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        items = [
            event.text
            for event in self._events
            if event.subject in query.subjects
        ]
        tokens = count_tokens("\n".join(items))
        return Retrieval(
            backend=self.name,
            query_id=query.query_id,
            retrieved_items=tuple(items),
            scanned_records=len(self._events),
            latency_ms=estimated_latency_ms(
                base_ms=14.0,
                scanned_records=len(self._events),
                retrieved_tokens=tokens,
            ),
        )

    def stored_text(self) -> str:
        return "\n".join(event.text for event in self._events)


class RecentWindowLog:
    """Short-context baseline: only the most recent raw memories are retained."""

    name = "recent_window_log"

    def __init__(self, window_size: int = 5) -> None:
        self._window_size = window_size
        self._events: list[MemoryEvent] = []

    def ingest(self, events: list[MemoryEvent]) -> None:
        self._events = list(events[-self._window_size :])

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        items = [
            event.text
            for event in self._events
            if event.subject in query.subjects
        ]
        tokens = count_tokens("\n".join(items))
        return Retrieval(
            backend=self.name,
            query_id=query.query_id,
            retrieved_items=tuple(items),
            scanned_records=len(self._events),
            latency_ms=estimated_latency_ms(
                base_ms=5.0,
                scanned_records=len(self._events),
                retrieved_tokens=tokens,
            ),
        )

    def stored_text(self) -> str:
        return "\n".join(event.text for event in self._events)


def build_dataset() -> list[MemoryEvent]:
    """Return the dense, shifting incident event stream."""

    return [
        MemoryEvent(
            1,
            "session-1",
            "checkout-api",
            "owner",
            "payments-oncall",
            "checkout-api owner is payments-oncall during the first rollout.",
        ),
        MemoryEvent(
            2,
            "session-1",
            "billing-cron",
            "owner",
            "analytics-platform-oncall",
            "billing-cron owner is analytics-platform-oncall; escalation is low.",
        ),
        MemoryEvent(
            3,
            "session-1",
            "checkout-api",
            "runbook",
            "restart-all-pods after clearing the queue",
            "checkout-api runbook says restart-all-pods after clearing the queue.",
        ),
        MemoryEvent(
            4,
            "session-1",
            "payments-ledger",
            "customer_message",
            "payments are failing for some customers",
            "payments-ledger customer message: payments are failing for some customers.",
        ),
        MemoryEvent(
            5,
            "session-2",
            "catalog-worker",
            "mitigation",
            "clear cache cluster before retrying the job",
            "catalog-worker mitigation was clear cache cluster before retrying.",
        ),
        MemoryEvent(
            6,
            "session-2",
            "search-indexer",
            "region",
            "us-east-1",
            "search-indexer failover region is us-east-1.",
        ),
        MemoryEvent(
            7,
            "session-3",
            "checkout-api",
            "debug_note",
            "debug credential sk_live_checkout_debug_123 must never be sent",
            "checkout-api debug note includes sk_live_checkout_debug_123 for a "
            "local replay, and the credential must never be sent to an agent.",
        ),
        MemoryEvent(
            8,
            "session-3",
            "checkout-api",
            "owner",
            "checkout-platform-oncall",
            "checkout-api owner changed to checkout-platform-oncall.",
        ),
        MemoryEvent(
            9,
            "session-3",
            "payments-ledger",
            "ops_note",
            "ledger lag is caused by partner settlement batching",
            "payments-ledger ops note: ledger lag is caused by settlement batching.",
        ),
        MemoryEvent(
            10,
            "session-4",
            "checkout-api",
            "runbook",
            "rollback checkout-canary and do not restart all pods",
            "checkout-api runbook changed: rollback checkout-canary and do not "
            "restart all pods.",
        ),
        MemoryEvent(
            11,
            "session-4",
            "payments-ledger",
            "customer_message",
            "payments post within 30 minutes after retry",
            "payments-ledger customer message changed: payments post within 30 "
            "minutes after retry.",
        ),
        MemoryEvent(
            12,
            "session-4",
            "catalog-worker",
            "mitigation",
            "raise redis TTL to 45 seconds",
            "catalog-worker mitigation changed: raise redis TTL to 45 seconds.",
        ),
        MemoryEvent(
            13,
            "session-5",
            "search-indexer",
            "region",
            "eu-west-1",
            "search-indexer failover region changed to eu-west-1.",
        ),
        MemoryEvent(
            14,
            "session-5",
            "deployment-window",
            "freeze",
            "stop non-emergency releases at 17:00 UTC",
            "deployment-window freeze: stop non-emergency releases at 17:00 UTC.",
        ),
    ]


def build_queries() -> list[GoldenQuery]:
    """Return current-state questions and conflict checks."""

    return [
        GoldenQuery(
            "q1_checkout_owner",
            "Who owns checkout-api right now?",
            ("checkout-api",),
            ("owner",),
            ("checkout-platform-oncall",),
            ("payments-oncall",),
        ),
        GoldenQuery(
            "q2_checkout_runbook",
            "Which runbook action should checkout-api use?",
            ("checkout-api",),
            ("runbook",),
            ("rollback checkout-canary",),
            ("restart-all-pods", "sk_live_checkout_debug_123"),
        ),
        GoldenQuery(
            "q3_payments_customer_message",
            "What should support say about payments-ledger retries?",
            ("payments-ledger",),
            ("customer_message",),
            ("payments post within 30 minutes",),
            ("payments are failing",),
        ),
        GoldenQuery(
            "q4_catalog_mitigation",
            "What mitigation is current for catalog-worker?",
            ("catalog-worker",),
            ("mitigation",),
            ("raise redis TTL to 45 seconds",),
            ("clear cache cluster",),
        ),
        GoldenQuery(
            "q5_search_region",
            "Where should search-indexer fail over now?",
            ("search-indexer",),
            ("region",),
            ("eu-west-1",),
            ("us-east-1",),
        ),
        GoldenQuery(
            "q6_billing_owner",
            "Who still owns billing-cron even though it was mentioned early?",
            ("billing-cron",),
            ("owner",),
            ("analytics-platform-oncall",),
            (),
        ),
        GoldenQuery(
            "q7_checkout_debug_secret",
            "What debug credential can be shown to the agent?",
            ("checkout-api",),
            ("debug_note",),
            ("[REDACTED_SECRET]",),
            ("sk_live_checkout_debug_123",),
        ),
    ]


def evaluate_retrieval(query: GoldenQuery, retrieval: Retrieval) -> dict[str, object]:
    """Score one retrieval against the golden answer."""

    context = "\n".join(retrieval.retrieved_items)
    context_lower = context.lower()
    expected_hit = all(term.lower() in context_lower for term in query.expected_terms)
    conflict_hit = any(term.lower() in context_lower for term in query.forbidden_terms)
    secret_hit = SECRET_PATTERN.search(context) is not None
    tokens = count_tokens(context)

    return {
        "query_id": query.query_id,
        "question": query.question,
        "backend": retrieval.backend,
        "correct": expected_hit and not conflict_hit and not secret_hit,
        "retrieved_tokens": tokens,
        "latency_ms": retrieval.latency_ms,
        "scanned_records": retrieval.scanned_records,
        "stale_conflict": conflict_hit,
        "secret_leak": secret_hit,
        "retrieved_items": list(retrieval.retrieved_items),
    }


def percentile(values: list[float], pct: float) -> float:
    """Return the nearest-rank percentile for deterministic small samples."""

    if not values:
        return 0.0

    sorted_values = sorted(values)
    rank = max(1, math.ceil((pct / 100.0) * len(sorted_values)))
    return sorted_values[rank - 1]


def summarize_backend(
    backend: MemoryBackend,
    events: list[MemoryEvent],
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Compute backend-level benchmark metrics."""

    total_queries = len(records)
    correct_count = sum(1 for record in records if record["correct"])
    conflict_count = sum(1 for record in records if record["stale_conflict"])
    secret_count = sum(1 for record in records if record["secret_leak"])
    retrieved_tokens = [int(record["retrieved_tokens"]) for record in records]
    latencies = [float(record["latency_ms"]) for record in records]
    stored_tokens = count_tokens(backend.stored_text())
    ingested_tokens = count_tokens("\n".join(event.text for event in events))

    return {
        "backend": backend.name,
        "retrieval_accuracy": round(correct_count / total_queries, 3),
        "correct_queries": correct_count,
        "total_queries": total_queries,
        "total_ingested_tokens": ingested_tokens,
        "stored_tokens": stored_tokens,
        "avg_retrieved_tokens": round(sum(retrieved_tokens) / total_queries, 3),
        "p95_latency_ms": round(percentile(latencies, 95), 3),
        "stale_conflict_rate": round(conflict_count / total_queries, 3),
        "secret_leak_rate": round(secret_count / total_queries, 3),
    }


def run_benchmark() -> dict[str, object]:
    """Run the benchmark and return a JSON-serializable result."""

    events = build_dataset()
    queries = build_queries()
    backends: list[MemoryBackend] = [
        ActiveIncidentDigest(),
        AppendOnlyLog(),
        RecentWindowLog(),
    ]

    metrics = []
    records = []
    for backend in backends:
        backend.ingest(events)
        backend_records = [
            evaluate_retrieval(query, backend.retrieve(query)) for query in queries
        ]
        records.extend(backend_records)
        metrics.append(summarize_backend(backend, events, backend_records))

    return {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "description": (
            "Dense incident-response memory with superseded runbooks, old owner "
            "state, retained early facts, and a synthetic leaked credential."
        ),
        "dataset": {
            "event_count": len(events),
            "query_count": len(queries),
            "sessions": sorted({event.session for event in events}),
        },
        "metrics": metrics,
        "records": records,
        "notes": [
            "All backends ingest the same ordered event stream.",
            "Latency is a deterministic local estimate derived from scanned "
            "records and retrieved tokens, not a hosted-provider stopwatch.",
            "The active digest models current-state memory behavior and redacts "
            "secrets before retrieval.",
        ],
    }


def write_json(result: dict[str, object], path: Path) -> None:
    """Write benchmark results as pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def format_percent(value: object) -> str:
    """Format a decimal metric as a percentage."""

    return f"{float(value) * 100:.1f}%"


def write_markdown(result: dict[str, object], path: Path) -> None:
    """Write a compact Markdown report."""

    metrics = result["metrics"]
    if not isinstance(metrics, list):
        raise TypeError("result['metrics'] must be a list")

    lines = [
        "# Incident Runbook Memory Benchmark",
        "",
        str(result["description"]),
        "",
        "## Summary",
        "",
        "| Backend | Retrieval accuracy | Avg retrieved tokens | "
        "p95 latency (ms) | Stale conflict rate | Secret leak rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for row in metrics:
        if not isinstance(row, dict):
            raise TypeError("metrics rows must be dictionaries")
        lines.append(
            "| {backend} | {accuracy} | {tokens:.1f} | {latency:.1f} | "
            "{conflicts} | {secrets} |".format(
                backend=row["backend"],
                accuracy=format_percent(row["retrieval_accuracy"]),
                tokens=float(row["avg_retrieved_tokens"]),
                latency=float(row["p95_latency_ms"]),
                conflicts=format_percent(row["stale_conflict_rate"]),
                secrets=format_percent(row["secret_leak_rate"]),
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `active_incident_digest` keeps only current facts per subject/key, "
            "so it avoids stale owner/runbook conflicts and redacts the "
            "synthetic credential before retrieval.",
            "- `append_only_log` preserves every raw event, which improves "
            "auditability but bloats retrieved context and surfaces superseded "
            "facts unless another layer filters them.",
            "- `recent_window_log` keeps context small, but it drops older facts "
            "that are still current, such as the billing-cron owner.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python run_benchmark.py --output results/sample_results.json "
            "--markdown results/sample_results.md",
            "```",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results") / "sample_results.json",
        help="Path for JSON benchmark results.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results") / "sample_results.md",
        help="Path for Markdown benchmark report.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    result = run_benchmark()
    write_json(result, args.output)
    write_markdown(result, args.markdown)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.markdown}")


if __name__ == "__main__":
    main()

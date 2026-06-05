from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass

from .backends import (
    AppendOnlyLogBackend,
    MemoryBackend,
    MemantoTypedDigestBackend,
    token_count,
)
from .dataset import IncidentQuery, IncidentRecord, incident_queries, incident_records


@dataclass(frozen=True)
class BackendResult:
    """Aggregate metrics for one memory backend."""

    backend: str
    tokens_ingested: int
    tokens_retrieved: int
    p95_latency_ms: float
    retrieval_accuracy: float
    stale_suppression: float
    signal_to_noise: float


@dataclass(frozen=True)
class QueryTrace:
    """Per-query context and scoring trace for a backend run."""

    backend: str
    prompt: str
    context: str
    expected_hits: int
    stale_hits: int
    latency_ms: float


@dataclass(frozen=True)
class BenchmarkReport:
    """Complete benchmark output with aggregate metrics and traces."""

    results: list[BackendResult]
    traces: list[QueryTrace]

    def to_json(self) -> str:
        """Serialize the benchmark report as stable JSON."""

        return json.dumps(
            {
                "results": [asdict(result) for result in self.results],
                "traces": [asdict(trace) for trace in self.traces],
            },
            indent=2,
            sort_keys=True,
        )

    def to_markdown(self) -> str:
        """Render the benchmark report as a Markdown table."""

        lines = [
            "# Incident Memory Pressure Benchmark Results",
            "",
            "| Backend | Tokens Ingested | Tokens Retrieved | p95 Latency (ms) | Retrieval Accuracy | Stale Suppression | Signal/Noise |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for result in self.results:
            lines.append(
                "| {backend} | {ingested} | {retrieved} | {latency:.3f} | "
                "{accuracy:.2%} | {stale:.2%} | {snr:.2%} |".format(
                    backend=result.backend,
                    ingested=result.tokens_ingested,
                    retrieved=result.tokens_retrieved,
                    latency=result.p95_latency_ms,
                    accuracy=result.retrieval_accuracy,
                    stale=result.stale_suppression,
                    snr=result.signal_to_noise,
                )
            )
        lines.extend(
            [
                "",
                "## Notes",
                "",
                "- Accuracy rewards current expected facts and penalizes stale facts.",
                "- Signal/noise rewards concise context that contains expected fact tokens.",
                "- The default run is credential-free and deterministic.",
            ]
        )
        return "\n".join(lines) + "\n"


def run_benchmark() -> BenchmarkReport:
    """Run every backend against the shared incident-memory dataset."""

    records = incident_records()
    queries = incident_queries()
    backends: list[MemoryBackend] = [
        MemantoTypedDigestBackend(),
        AppendOnlyLogBackend(),
    ]

    results: list[BackendResult] = []
    traces: list[QueryTrace] = []
    for backend in backends:
        backend.ingest(records)
        backend_result, backend_traces = _evaluate_backend(backend, records, queries)
        results.append(backend_result)
        traces.extend(backend_traces)
    return BenchmarkReport(results=results, traces=traces)


def _evaluate_backend(
    backend: MemoryBackend,
    records: list[IncidentRecord],
    queries: list[IncidentQuery],
) -> tuple[BackendResult, list[QueryTrace]]:
    """Score one backend across the benchmark query set."""

    tokens_ingested = sum(token_count(record.text) for record in records)
    tokens_retrieved = 0
    expected_total = 0
    expected_hits = 0
    stale_total = 0
    stale_hits = 0
    signal_tokens = 0
    latencies: list[float] = []
    traces: list[QueryTrace] = []

    for query in queries:
        start = time.perf_counter()
        hits = backend.recall(query)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)
        context = "\n".join(hit.text for hit in hits)
        context_folded = context.casefold()
        retrieved_tokens = sum(hit.tokens for hit in hits)
        tokens_retrieved += retrieved_tokens

        query_expected_hits = sum(
            1 for fragment in query.expected_fragments if fragment.casefold() in context_folded
        )
        query_stale_hits = sum(
            1 for fragment in query.stale_fragments if fragment.casefold() in context_folded
        )
        expected_total += len(query.expected_fragments)
        expected_hits += query_expected_hits
        stale_total += len(query.stale_fragments)
        stale_hits += query_stale_hits
        signal_tokens += sum(token_count(fragment) for fragment in query.expected_fragments)

        traces.append(
            QueryTrace(
                backend=backend.name,
                prompt=query.prompt,
                context=context,
                expected_hits=query_expected_hits,
                stale_hits=query_stale_hits,
                latency_ms=latency_ms,
            )
        )

    accuracy_denominator = expected_total + stale_total
    accuracy = (
        (expected_hits + (stale_total - stale_hits)) / accuracy_denominator
        if accuracy_denominator
        else 0.0
    )
    stale_suppression = (
        (stale_total - stale_hits) / stale_total if stale_total else 1.0
    )
    p95_latency = _p95(latencies)
    signal_to_noise = signal_tokens / max(tokens_retrieved, 1)
    return (
        BackendResult(
            backend=backend.name,
            tokens_ingested=tokens_ingested,
            tokens_retrieved=tokens_retrieved,
            p95_latency_ms=p95_latency,
            retrieval_accuracy=accuracy,
            stale_suppression=stale_suppression,
            signal_to_noise=signal_to_noise,
        ),
        traces,
    )


def _p95(values: list[float]) -> float:
    """Return a simple nearest-rank p95 latency value."""

    if len(values) < 2:
        return values[0] if values else 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(math.ceil(len(sorted_values) * 0.95)) - 1)
    return sorted_values[index]

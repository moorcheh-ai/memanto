"""Benchmark runner: N runs per backend per scenario, collect metrics.

Outputs:
  - Per-run: accuracy, p50/p95 latency, tokens_written, tokens_retrieved
  - Aggregate: mean ± std, accuracy %, staleness-penalty score
"""
from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from .backends.base import MemoryBackend
from .dataset import SCENARIOS, Scenario
from .judge import score_answer


@dataclass
class RunRecord:
    scenario: str
    run_index: int
    backend: str
    latency_ingest_ms: list[float]
    latency_retrieve_ms: list[float]
    tokens_written: int
    tokens_retrieved: int
    probe_scores: list[float]

    @property
    def accuracy(self) -> float:
        if not self.probe_scores:
            return 0.0
        return sum(self.probe_scores) / len(self.probe_scores)

    @property
    def p50_ingest_ms(self) -> float:
        return _percentile(self.latency_ingest_ms, 50)

    @property
    def p95_ingest_ms(self) -> float:
        return _percentile(self.latency_ingest_ms, 95)

    @property
    def p50_retrieve_ms(self) -> float:
        return _percentile(self.latency_retrieve_ms, 50)

    @property
    def p95_retrieve_ms(self) -> float:
        return _percentile(self.latency_retrieve_ms, 95)


@dataclass
class BackendSummary:
    backend: str
    n_runs: int
    n_scenarios: int
    accuracy_mean: float
    accuracy_std: float
    tokens_written_mean: float
    tokens_retrieved_mean: float
    ingest_p50_mean: float
    ingest_p95_mean: float
    retrieve_p50_mean: float
    retrieve_p95_mean: float
    records: list[RunRecord] = field(default_factory=list)


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    data_sorted = sorted(data)
    idx = (len(data_sorted) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(data_sorted) - 1)
    frac = idx - lo
    return data_sorted[lo] + frac * (data_sorted[hi] - data_sorted[lo])


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def run_benchmark(
    backends: list[MemoryBackend],
    n_runs: int = 3,
    scenarios: list[Scenario] | None = None,
    verbose: bool = True,
) -> list[BackendSummary]:
    """Run the full benchmark.

    Parameters
    ----------
    backends:   List of MemoryBackend instances to compare.
    n_runs:     Number of independent runs per (backend, scenario) pair.
    scenarios:  Which scenarios to run. Defaults to all 6.
    verbose:    Print progress to stdout.

    Returns
    -------
    List of BackendSummary, one per backend.
    """
    if scenarios is None:
        scenarios = SCENARIOS

    summaries: list[BackendSummary] = []

    for backend in backends:
        if verbose:
            print(f"\n{'='*60}")
            print(f"Backend: {backend.name}")
            print(f"{'='*60}")

        all_records: list[RunRecord] = []

        for scenario in scenarios:
            for run_idx in range(n_runs):
                if verbose:
                    print(
                        f"  scenario={scenario.name!r}  run={run_idx+1}/{n_runs} ... ",
                        end="",
                        flush=True,
                    )

                backend.reset()
                record = _run_once(backend, scenario, run_idx)
                all_records.append(record)

                if verbose:
                    print(f"acc={record.accuracy:.2f}")

        # Aggregate
        accuracies = [r.accuracy for r in all_records]
        tokens_w = [r.tokens_written for r in all_records]
        tokens_r = [r.tokens_retrieved for r in all_records]
        ingest_p50s = [r.p50_ingest_ms for r in all_records]
        ingest_p95s = [r.p95_ingest_ms for r in all_records]
        retrieve_p50s = [r.p50_retrieve_ms for r in all_records]
        retrieve_p95s = [r.p95_retrieve_ms for r in all_records]

        summaries.append(
            BackendSummary(
                backend=backend.name,
                n_runs=n_runs,
                n_scenarios=len(scenarios),
                accuracy_mean=sum(accuracies) / len(accuracies) if accuracies else 0.0,
                accuracy_std=_std(accuracies),
                tokens_written_mean=sum(tokens_w) / len(tokens_w) if tokens_w else 0.0,
                tokens_retrieved_mean=sum(tokens_r) / len(tokens_r) if tokens_r else 0.0,
                ingest_p50_mean=sum(ingest_p50s) / len(ingest_p50s) if ingest_p50s else 0.0,
                ingest_p95_mean=sum(ingest_p95s) / len(ingest_p95s) if ingest_p95s else 0.0,
                retrieve_p50_mean=sum(retrieve_p50s) / len(retrieve_p50s) if retrieve_p50s else 0.0,
                retrieve_p95_mean=sum(retrieve_p95s) / len(retrieve_p95s) if retrieve_p95s else 0.0,
                records=all_records,
            )
        )

    return summaries


def _run_once(backend: MemoryBackend, scenario: Scenario, run_idx: int) -> RunRecord:
    """Execute a single run of a scenario against a backend."""
    user_id = f"u_{scenario.name}_{run_idx}"
    ingest_latencies: list[float] = []
    retrieve_latencies: list[float] = []
    total_written = 0

    # Ingest all history
    for turn in scenario.history:
        result = backend.ingest(user_id=user_id, content=turn)
        ingest_latencies.append(result.latency_ms)
        total_written += result.tokens_written

    # Probe
    probe_scores: list[float] = []
    total_retrieved = 0
    for probe in scenario.probes:
        result = backend.retrieve(user_id=user_id, query=probe.query)
        retrieve_latencies.append(result.latency_ms)
        total_retrieved += result.tokens_retrieved
        score = score_answer(
            context=result.context,
            query=probe.query,
            expected_keyword=probe.expected_keyword,
            explanation=probe.explanation,
            stale_keyword=probe.stale_keyword,
        )
        probe_scores.append(score)

    return RunRecord(
        scenario=scenario.name,
        run_index=run_idx,
        backend=backend.name,
        latency_ingest_ms=ingest_latencies,
        latency_retrieve_ms=retrieve_latencies,
        tokens_written=total_written,
        tokens_retrieved=total_retrieved,
        probe_scores=probe_scores,
    )

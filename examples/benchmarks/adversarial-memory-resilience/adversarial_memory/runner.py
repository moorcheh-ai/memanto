"""Benchmark orchestration, traces, aggregation, and reporting."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import platform
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from .adapters import MemoryAdapter, create_adapter
from .dataset import generate_scenario
from .scoring import (
    ProbeScore,
    approximate_tokens,
    paired_bootstrap_ci,
    percentile,
    score_probe,
)


def _package_version(package: str) -> str:
    """Return an installed package version without requiring optional backends."""

    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


@dataclass(frozen=True)
class BenchmarkConfig:
    """Reproducible experiment controls."""

    backends: tuple[str, ...] = ("memanto", "mem0")
    seeds: tuple[int, ...] = (7, 19, 43)
    tenants: int = 3
    incidents: int = 4
    revisions: int = 4
    top_k: int = 5
    output_dir: Path = Path("results")
    cleanup: bool = True


@dataclass(frozen=True)
class Trace:
    backend: str
    seed: int
    probe_id: str
    latency_seconds: float
    hit: bool
    reciprocal_rank: float
    stale_exposure: bool
    poison_exposure: bool
    foreign_exposure: bool
    retrieved_tokens: int


def _run_one(
    *,
    config: BenchmarkConfig,
    backend: str,
    seed: int,
    work_dir: Path,
    adapter_factory=create_adapter,
) -> tuple[list[Trace], list[float], int]:
    scenario = generate_scenario(
        seed=seed,
        tenants=config.tenants,
        incidents=config.incidents,
        revisions=config.revisions,
    )
    tenants = tuple(sorted({event.tenant for event in scenario.events}))
    run_id = f"{backend}-{seed}-{uuid.uuid4().hex[:8]}"
    adapter: MemoryAdapter = adapter_factory(
        backend,
        run_id=run_id,
        tenants=tenants,
        work_dir=work_dir,
        cleanup=config.cleanup,
    )
    traces: list[Trace] = []
    write_latencies: list[float] = []
    ingested_tokens = 0
    try:
        for session in range(config.revisions):
            for event in (item for item in scenario.events if item.session == session):
                started = time.perf_counter()
                adapter.add(event)
                write_latencies.append(time.perf_counter() - started)
                ingested_tokens += approximate_tokens(event.content)
            for probe in (item for item in scenario.probes if item.session == session):
                started = time.perf_counter()
                retrieved = adapter.search(probe, limit=config.top_k)
                latency = time.perf_counter() - started
                score: ProbeScore = score_probe(probe, retrieved)
                traces.append(
                    Trace(
                        backend=backend,
                        seed=seed,
                        probe_id=probe.probe_id,
                        latency_seconds=latency,
                        **asdict(score),
                    )
                )
    finally:
        adapter.close()
    return traces, write_latencies, ingested_tokens


def summarize(
    traces: list[Trace], write_latencies: dict[str, list[float]], tokens: dict[str, int]
) -> list[dict[str, float | int | str]]:
    """Aggregate the required and adversarial metrics per backend."""

    rows: list[dict[str, float | int | str]] = []
    for backend in sorted({trace.backend for trace in traces}):
        selected = [trace for trace in traces if trace.backend == backend]
        rows.append(
            {
                "backend": backend,
                "probes": len(selected),
                "retrieval_accuracy": mean(trace.hit for trace in selected),
                "mean_reciprocal_rank": mean(
                    trace.reciprocal_rank for trace in selected
                ),
                "stale_exposure_rate": mean(trace.stale_exposure for trace in selected),
                "poison_exposure_rate": mean(
                    trace.poison_exposure for trace in selected
                ),
                "foreign_exposure_rate": mean(
                    trace.foreign_exposure for trace in selected
                ),
                "tokens_ingested": tokens[backend],
                "mean_tokens_retrieved": mean(
                    trace.retrieved_tokens for trace in selected
                ),
                "p95_write_latency_seconds": percentile(write_latencies[backend], 95),
                "p95_retrieval_latency_seconds": percentile(
                    [trace.latency_seconds for trace in selected], 95
                ),
            }
        )
    return rows


def compare_backends(
    traces: list[Trace], *, left: str, right: str
) -> dict[str, dict[str, float]]:
    """Compute deterministic paired confidence intervals over identical probes."""

    keyed = {(trace.backend, trace.seed, trace.probe_id): trace for trace in traces}
    pairs = sorted(
        (seed, probe_id)
        for backend, seed, probe_id in keyed
        if backend == left and (right, seed, probe_id) in keyed
    )
    if not pairs:
        raise ValueError(f"no paired traces for {left} and {right}")
    result: dict[str, dict[str, float]] = {}
    metrics = {
        "hit": "hit",
        "reciprocal_rank": "reciprocal_rank",
        "stale_exposure": "stale_exposure",
        "poison_exposure": "poison_exposure",
        "foreign_exposure": "foreign_exposure",
        "retrieved_tokens": "retrieved_tokens",
        "mean_retrieval_latency_seconds": "latency_seconds",
    }
    for output_name, trace_attribute in metrics.items():
        left_values = [
            float(getattr(keyed[(left, *pair)], trace_attribute)) for pair in pairs
        ]
        right_values = [
            float(getattr(keyed[(right, *pair)], trace_attribute)) for pair in pairs
        ]
        estimate, low, high = paired_bootstrap_ci(
            left_values, right_values, seed=20260605
        )
        result[output_name] = {
            "mean_delta_left_minus_right": estimate,
            "ci95_low": low,
            "ci95_high": high,
        }
    return result


def _report(
    summary: list[dict[str, float | int | str]],
    comparison: dict[str, dict[str, float]],
    *,
    left: str,
    right: str,
) -> str:
    """Render a compact, auditable Markdown report."""

    lines = [
        "# Adversarial memory resilience benchmark",
        "",
        "All values come from live backends over identical seeded workloads.",
        "Marker matching is deterministic; no LLM judge is used.",
        "",
        "| Backend | Accuracy | MRR | Stale exposure | Poison exposure | "
        "Foreign exposure | Retrieved tokens | p95 retrieval (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['backend']} | {row['retrieval_accuracy']:.3f} | "
            f"{row['mean_reciprocal_rank']:.3f} | "
            f"{row['stale_exposure_rate']:.3f} | "
            f"{row['poison_exposure_rate']:.3f} | "
            f"{row['foreign_exposure_rate']:.3f} | "
            f"{row['mean_tokens_retrieved']:.1f} | "
            f"{row['p95_retrieval_latency_seconds']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"## Paired effects ({left} minus {right})",
            "",
            "| Metric | Mean delta | 95% bootstrap CI |",
            "|---|---:|---:|",
        ]
    )
    for metric, values in comparison.items():
        lines.append(
            f"| {metric} | {values['mean_delta_left_minus_right']:.6f} | "
            f"[{values['ci95_low']:.6f}, {values['ci95_high']:.6f}] |"
        )
    lines.extend(
        [
            "",
            "Lower is better for stale, poison, foreign exposure, retrieved tokens, "
            "and latency. Higher is better for hit rate and reciprocal rank.",
            "The latency effect is the paired mean retrieval-latency delta; backend "
            "p95 write and retrieval latencies are reported separately above and in "
            "summary.json.",
            "",
        ]
    )
    return "\n".join(lines)


def run_benchmark(config: BenchmarkConfig) -> Path:
    """Run all paired trials and write machine-readable artifacts."""

    if len(config.backends) < 2:
        raise ValueError("at least two backends are required")
    if not config.seeds:
        raise ValueError("at least one seed is required")
    output = config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    work_dir = output / "work"
    work_dir.mkdir(exist_ok=True)
    traces: list[Trace] = []
    write_latencies = {backend: [] for backend in config.backends}
    tokens = dict.fromkeys(config.backends, 0)
    for seed in config.seeds:
        for backend in config.backends:
            run_traces, run_writes, run_tokens = _run_one(
                config=config,
                backend=backend,
                seed=seed,
                work_dir=work_dir,
            )
            traces.extend(run_traces)
            write_latencies[backend].extend(run_writes)
            tokens[backend] += run_tokens
    summary = summarize(traces, write_latencies, tokens)
    left, right = config.backends[:2]
    comparison = compare_backends(traces, left=left, right=right)
    (output / "config.json").write_text(
        json.dumps({**asdict(config), "output_dir": str(config.output_dir)}, indent=2),
        encoding="utf-8",
    )
    (output / "environment.json").write_text(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "processor": platform.processor(),
                "packages": {
                    package: _package_version(package)
                    for package in ("memanto", "mem0ai", "fastembed", "qdrant-client")
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output / "traces.jsonl").open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(asdict(trace)) + "\n")
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )
    (output / "report.md").write_text(
        _report(summary, comparison, left=left, right=right), encoding="utf-8"
    )
    with (output / "dataset.jsonl").open("w", encoding="utf-8") as handle:
        for seed in config.seeds:
            scenario = generate_scenario(
                seed=seed,
                tenants=config.tenants,
                incidents=config.incidents,
                revisions=config.revisions,
            )
            for event in scenario.events:
                handle.write(json.dumps({"seed": seed, "event": asdict(event)}) + "\n")
            for probe in scenario.probes:
                handle.write(json.dumps({"seed": seed, "probe": asdict(probe)}) + "\n")
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return output

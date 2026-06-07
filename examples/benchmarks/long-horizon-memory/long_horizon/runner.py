"""Paired benchmark runner and artifact generation."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import MemoryAdapter, create_adapter
from .dataset import Probe, generate_scenario
from .scoring import (
    ProbeScore,
    bootstrap_mean_ci,
    percentile,
    score_probe,
)

AdapterFactory = Callable[..., MemoryAdapter]
TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class BenchmarkConfig:
    backends: tuple[str, ...] = ("memanto", "mem0")
    seeds: tuple[int, ...] = (7, 19, 43)
    sessions: int = 48
    checkpoints: tuple[int, ...] = (8, 16, 24, 32, 48)
    top_k: int = 5
    output_dir: Path = Path("results")
    cleanup: bool = True


def _default_token_counter() -> TokenCounter:
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError(
            "tiktoken is required for normalized context token counts. "
            "Install requirements.txt before running the benchmark."
        ) from exc
    encoding = tiktoken.get_encoding("cl100k_base")
    return lambda text: len(encoding.encode(text))


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _source_manifest() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[4]

    def git_output(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ("git", *args),
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip() or None

    status = git_output("status", "--porcelain", "--untracked-files=no")
    return {
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_tracked_files_dirty": bool(status),
    }


def _environment_manifest() -> dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "source": _source_manifest(),
        "packages": {
            name: _package_version(name)
            for name in (
                "memanto",
                "mem0ai",
                "certifi",
                "fastembed",
                "openai",
                "qdrant-client",
                "tiktoken",
            )
        },
        "models": {
            "mem0_llm": "disabled (infer=False)",
            "mem0_telemetry": "disabled",
            "mem0_embedding_weights": "sentence-transformers/all-MiniLM-L6-v2",
            "mem0_embedding": os.environ.get(
                "MEM0_EMBEDDING_MODEL",
                "benchmark/all-MiniLM-L6-v2",
            ),
            "mem0_embedding_dims": int(os.environ.get("MEM0_EMBEDDING_DIMS", "384")),
        },
    }


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _score_to_dict(score: ProbeScore) -> dict[str, Any]:
    return asdict(score)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _summarize_backend(
    backend: str,
    probe_rows: list[dict[str, Any]],
    write_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    top1 = [float(row["top1_correct"]) for row in probe_rows]
    strict = [float(row["strict_correct"]) for row in probe_rows]
    current = [float(row["current_recalled"]) for row in probe_rows]
    stale = [float(row["stale_conflict"]) for row in probe_rows]
    reciprocal = [float(row["reciprocal_rank"]) for row in probe_rows]
    tokens = [float(row["retrieved_tokens"]) for row in probe_rows]
    ratios = [float(row["signal_to_noise"]) for row in probe_rows]
    read_latency = [float(row["latency_ms"]) for row in probe_rows]
    write_latency = [
        float(row["latency_ms"]) for row in write_rows if row["backend"] == backend
    ]
    input_tokens = [
        int(row["input_tokens"]) for row in write_rows if row["backend"] == backend
    ]
    top1_ci_low, top1_ci_high = bootstrap_mean_ci(top1)
    strict_ci_low, strict_ci_high = bootstrap_mean_ci(strict)

    checkpoints: dict[str, Any] = {}
    for checkpoint in sorted({int(row["checkpoint"]) for row in probe_rows}):
        rows = [row for row in probe_rows if int(row["checkpoint"]) == checkpoint]
        checkpoint_top1 = [float(row["top1_correct"]) for row in rows]
        checkpoint_strict = [float(row["strict_correct"]) for row in rows]
        checkpoints[str(checkpoint)] = {
            "n": len(rows),
            "top1_accuracy": sum(checkpoint_top1) / len(checkpoint_top1),
            "strict_accuracy": sum(checkpoint_strict) / len(checkpoint_strict),
            "current_recall": sum(float(row["current_recalled"]) for row in rows)
            / len(rows),
            "stale_conflict_rate": sum(float(row["stale_conflict"]) for row in rows)
            / len(rows),
            "mean_retrieved_tokens": sum(float(row["retrieved_tokens"]) for row in rows)
            / len(rows),
        }

    return {
        "backend": backend,
        "n_probes": len(probe_rows),
        "n_writes": len(write_latency),
        "top1_accuracy": sum(top1) / len(top1),
        "top1_accuracy_ci95": [top1_ci_low, top1_ci_high],
        "strict_accuracy": sum(strict) / len(strict),
        "strict_accuracy_ci95": [strict_ci_low, strict_ci_high],
        "current_recall": sum(current) / len(current),
        "stale_conflict_rate": sum(stale) / len(stale),
        "mean_reciprocal_rank": sum(reciprocal) / len(reciprocal),
        "mean_retrieved_tokens": sum(tokens) / len(tokens),
        "total_retrieved_tokens": int(sum(tokens)),
        "total_ingested_tokens": sum(input_tokens),
        "mean_signal_to_noise": sum(ratios) / len(ratios),
        "read_latency_ms": {
            "p50": percentile(read_latency, 50),
            "p95": percentile(read_latency, 95),
            "p99": percentile(read_latency, 99),
        },
        "write_latency_ms": {
            "p50": percentile(write_latency, 50),
            "p95": percentile(write_latency, 95),
            "p99": percentile(write_latency, 99),
        },
        "by_checkpoint": checkpoints,
    }


def _paired_comparison(
    backend_a: str,
    backend_b: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_backend: dict[str, dict[tuple[int, int, str], float]] = defaultdict(dict)
    for row in rows:
        key = (int(row["seed"]), int(row["checkpoint"]), str(row["fact_key"]))
        by_backend[str(row["backend"])][key] = float(row["top1_correct"])
    common = sorted(set(by_backend[backend_a]) & set(by_backend[backend_b]))
    differences = [
        by_backend[backend_a][key] - by_backend[backend_b][key] for key in common
    ]
    ci_low, ci_high = bootstrap_mean_ci(differences, seed=20260607)
    return {
        "metric": "paired_top1_accuracy_difference",
        "backend_a": backend_a,
        "backend_b": backend_b,
        "n_pairs": len(common),
        "mean_difference": (
            0.0 if not differences else sum(differences) / len(differences)
        ),
        "ci95": [ci_low, ci_high],
    }


def _markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Long-Horizon Agent Memory Benchmark",
        "",
        f"Run: `{summary['run_id']}`",
        "",
        "This report compares real memory backends on the same ordered event",
        "stream. Higher accuracy and signal-to-noise are better; lower stale",
        "conflict, token footprint, and latency are better.",
        "",
        "| Backend | Top-1 accuracy | Top-k current recall | Stale context | "
        "Clean-context recall | "
        "Mean context tokens | Total context tokens | Signal/noise | "
        "Read p95 ms | Write p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for backend in summary["backends"]:
        lines.append(
            "| {backend} | {top1:.1%} | {current:.1%} | {stale:.1%} | "
            "{strict:.1%} | "
            "{tokens:.1f} | {total_tokens} | {ratio:.3f} | {read:.1f} | "
            "{write:.1f} |".format(
                backend=backend["backend"],
                top1=backend["top1_accuracy"],
                strict=backend["strict_accuracy"],
                current=backend["current_recall"],
                stale=backend["stale_conflict_rate"],
                tokens=backend["mean_retrieved_tokens"],
                total_tokens=backend["total_retrieved_tokens"],
                ratio=backend["mean_signal_to_noise"],
                read=backend["read_latency_ms"]["p95"],
                write=backend["write_latency_ms"]["p95"],
            )
        )
    lines.extend(
        (
            "",
            "## Accuracy by checkpoint",
            "",
            "| Backend | Checkpoint | Top-1 accuracy | Top-k current recall | "
            "Stale context | Clean-context recall | Mean context tokens |",
            "|---|---:|---:|---:|---:|---:|---:|",
        )
    )
    for backend in summary["backends"]:
        for checkpoint, metrics in backend["by_checkpoint"].items():
            lines.append(
                "| {backend} | {checkpoint} | {top1:.1%} | {current:.1%} | "
                "{stale:.1%} | {strict:.1%} | {tokens:.1f} |".format(
                    backend=backend["backend"],
                    checkpoint=checkpoint,
                    top1=metrics["top1_accuracy"],
                    strict=metrics["strict_accuracy"],
                    current=metrics["current_recall"],
                    stale=metrics["stale_conflict_rate"],
                    tokens=metrics["mean_retrieved_tokens"],
                )
            )
    if summary.get("paired_comparison"):
        comparison = summary["paired_comparison"]
        lines.extend(
            (
                "",
                "## Paired comparison",
                "",
                (
                    "`{backend_a} - {backend_b}` Top-1 accuracy difference: "
                    "**{difference:+.1%}** (95% bootstrap CI "
                    "`[{low:+.1%}, {high:+.1%}]`, n={count})."
                ).format(
                    backend_a=comparison["backend_a"],
                    backend_b=comparison["backend_b"],
                    difference=comparison["mean_difference"],
                    low=comparison["ci95"][0],
                    high=comparison["ci95"][1],
                    count=comparison["n_pairs"],
                ),
            )
        )
    lines.extend(
        (
            "",
            "## Reproduction",
            "",
            "See `config.json`, `environment.json`, and `raw_traces.jsonl` in",
            "this directory. Raw traces preserve every query, returned context,",
            "latency measurement, and deterministic score.",
            "",
        )
    )
    return "\n".join(lines)


def _write_summary_csv(path: Path, backends: list[dict[str, Any]]) -> None:
    columns = (
        "backend",
        "n_probes",
        "top1_accuracy",
        "strict_accuracy",
        "current_recall",
        "stale_conflict_rate",
        "mean_reciprocal_rank",
        "mean_retrieved_tokens",
        "total_retrieved_tokens",
        "total_ingested_tokens",
        "mean_signal_to_noise",
        "read_p50_ms",
        "read_p95_ms",
        "write_p50_ms",
        "write_p95_ms",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for backend in backends:
            writer.writerow(
                {
                    "backend": backend["backend"],
                    "n_probes": backend["n_probes"],
                    "top1_accuracy": backend["top1_accuracy"],
                    "strict_accuracy": backend["strict_accuracy"],
                    "current_recall": backend["current_recall"],
                    "stale_conflict_rate": backend["stale_conflict_rate"],
                    "mean_reciprocal_rank": backend["mean_reciprocal_rank"],
                    "mean_retrieved_tokens": backend["mean_retrieved_tokens"],
                    "total_retrieved_tokens": backend["total_retrieved_tokens"],
                    "total_ingested_tokens": backend["total_ingested_tokens"],
                    "mean_signal_to_noise": backend["mean_signal_to_noise"],
                    "read_p50_ms": backend["read_latency_ms"]["p50"],
                    "read_p95_ms": backend["read_latency_ms"]["p95"],
                    "write_p50_ms": backend["write_latency_ms"]["p50"],
                    "write_p95_ms": backend["write_latency_ms"]["p95"],
                }
            )


def run_benchmark(
    config: BenchmarkConfig,
    *,
    adapter_factory: AdapterFactory = create_adapter,
    token_counter: TokenCounter | None = None,
    run_id: str | None = None,
) -> Path:
    """Run all backends against paired event streams and write artifacts."""
    if len(config.backends) < 1:
        raise ValueError("at least one backend is required")
    if len(set(config.backends)) != len(config.backends):
        raise ValueError("backends must be unique")
    if len(config.seeds) < 1:
        raise ValueError("at least one seed is required")
    if len(config.checkpoints) < 1:
        raise ValueError("at least one checkpoint is required")
    if config.top_k < 1:
        raise ValueError("top_k must be positive")
    run_id = run_id or _new_run_id()
    output = config.output_dir / run_id
    output.mkdir(parents=True, exist_ok=False)
    work_dir = output / "backend-state"
    work_dir.mkdir()
    count_tokens = token_counter or _default_token_counter()

    probe_rows: list[dict[str, Any]] = []
    write_rows: list[dict[str, Any]] = []

    for seed in config.seeds:
        events, probes = generate_scenario(
            seed=seed,
            sessions=config.sessions,
            checkpoints=config.checkpoints,
        )
        probes_by_checkpoint: dict[int, list[Probe]] = defaultdict(list)
        for probe in probes:
            probes_by_checkpoint[probe.checkpoint].append(probe)

        adapters: dict[str, MemoryAdapter] = {}
        try:
            for backend in config.backends:
                adapters[backend] = adapter_factory(
                    backend,
                    run_id=f"{run_id}-seed-{seed}-{backend}",
                    work_dir=work_dir,
                    cleanup=config.cleanup,
                )

            for event in events:
                write_order = list(config.backends)
                random.Random(seed * 1000 + event.session).shuffle(write_order)
                for backend in write_order:
                    started = time.perf_counter()
                    adapters[backend].add(event)
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    write_rows.append(
                        {
                            "backend": backend,
                            "seed": seed,
                            "session": event.session,
                            "event_id": event.event_id,
                            "fact_key": event.fact_key,
                            "input_tokens": count_tokens(event.content),
                            "latency_ms": elapsed_ms,
                        }
                    )

                for probe in probes_by_checkpoint.get(event.session, []):
                    read_order = list(config.backends)
                    random.Random(
                        seed * 100000 + event.session * 100 + len(probe_rows)
                    ).shuffle(read_order)
                    for backend in read_order:
                        started = time.perf_counter()
                        items = list(
                            adapters[backend].search(probe, limit=config.top_k)
                        )
                        elapsed_ms = (time.perf_counter() - started) * 1000.0
                        score = score_probe(probe, items, count_tokens)
                        probe_rows.append(
                            {
                                "backend": backend,
                                "seed": seed,
                                "checkpoint": probe.checkpoint,
                                "probe_id": probe.probe_id,
                                "fact_key": probe.fact_key,
                                "query": probe.query,
                                "expected_value": probe.expected_value,
                                "stale_values": list(probe.stale_values),
                                "latency_ms": elapsed_ms,
                                **_score_to_dict(score),
                                "retrieved": [
                                    {
                                        "rank": item.rank,
                                        "score": item.score,
                                        "text": item.text,
                                    }
                                    for item in items
                                ],
                            }
                        )
        finally:
            active_error = sys.exc_info()[0] is not None
            cleanup_errors = []
            for backend, adapter in adapters.items():
                try:
                    adapter.close()
                except Exception as exc:
                    cleanup_errors.append(f"{backend}: {exc}")
            if cleanup_errors and not active_error:
                raise RuntimeError(
                    "backend cleanup failed: " + "; ".join(cleanup_errors)
                )

    backend_summaries = []
    for backend in config.backends:
        rows = [row for row in probe_rows if row["backend"] == backend]
        backend_summaries.append(_summarize_backend(backend, rows, write_rows))

    summary: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backends": backend_summaries,
    }
    if len(config.backends) == 2:
        summary["paired_comparison"] = _paired_comparison(
            config.backends[0],
            config.backends[1],
            probe_rows,
        )

    config_data = asdict(config)
    config_data["output_dir"] = str(config.output_dir)
    _write_json(output / "config.json", config_data)
    _write_json(output / "environment.json", _environment_manifest())
    _write_jsonl(output / "raw_traces.jsonl", probe_rows)
    _write_jsonl(output / "write_traces.jsonl", write_rows)
    _write_json(output / "summary.json", summary)
    _write_summary_csv(output / "summary.csv", backend_summaries)
    (output / "report.md").write_text(_markdown_report(summary), encoding="utf-8")
    return output

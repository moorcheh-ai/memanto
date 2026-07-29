"""Run a live, paired Memanto versus Mem0 temporal-memory benchmark."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import psutil
from backends import (
    Mem0Backend,
    MemantoBackend,
    MemoryBackend,
    new_run_id,
    wait_until_searchable,
)
from dataset import QUERIES, RECORDS
from metrics import (
    count_tokens,
    paired_bootstrap_delta,
    percentile,
    score_query,
    summarize_scores,
)

HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark real Memanto and Mem0 memory backends."
    )
    parser.add_argument(
        "--backends",
        default="memanto,mem0-direct,mem0-agentic",
        help="Comma-separated: memanto, mem0-direct, mem0-agentic",
    )
    parser.add_argument("--moorcheh-url", default="http://127.0.0.1:8080")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-model", default="qwen2.5:1.5b")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--ready-timeout", type=float, default=180.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "results" / "latest.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=HERE / "results" / "latest.md",
    )
    return parser.parse_args()


def build_backend(name: str, args: argparse.Namespace, run_id: str) -> MemoryBackend:
    if name == "memanto":
        return MemantoBackend(args.moorcheh_url, run_id)
    if name == "mem0-direct":
        return Mem0Backend(
            ollama_url=args.ollama_url,
            llm_model=args.llm_model,
            run_id=run_id,
            infer=False,
            work_dir=HERE / ".benchmark-data",
        )
    if name == "mem0-agentic":
        return Mem0Backend(
            ollama_url=args.ollama_url,
            llm_model=args.llm_model,
            run_id=run_id,
            infer=True,
            work_dir=HERE / ".benchmark-data",
        )
    raise ValueError(f"Unknown backend: {name}")


def run_backend(
    backend: MemoryBackend,
    *,
    top_k: int,
    repeats: int,
    ready_timeout: float,
) -> dict[str, Any]:
    process = psutil.Process()
    rss_before = process.memory_info().rss
    ingest_latencies: list[float] = []

    for record in RECORDS:
        started = time.perf_counter()
        backend.ingest(record)
        ingest_latencies.append(time.perf_counter() - started)

    ready_latency = wait_until_searchable(
        backend,
        query="What is the current mission call sign?",
        expected="Lumen",
        top_k=top_k,
        timeout_s=ready_timeout,
    )

    for case in QUERIES:
        backend.search(case.query, top_k)

    query_latencies: list[float] = []
    query_rows = []
    retrieved_tokens = 0
    scores = []
    for repeat in range(repeats):
        for case in QUERIES:
            started = time.perf_counter()
            hits = backend.search(case.query, top_k)
            query_latencies.append(time.perf_counter() - started)
            if repeat != 0:
                continue

            combined = "\n".join(hit.text for hit in hits)
            tokens = count_tokens(combined)
            retrieved_tokens += tokens
            score = score_query(case, combined)
            scores.append(score)
            query_rows.append(
                {
                    "query_id": case.query_id,
                    "category": case.category,
                    "query": case.query,
                    "retrieved_tokens": tokens,
                    "score": score.to_dict(),
                    "hits": [asdict(hit) for hit in hits],
                }
            )

    rss_after = process.memory_info().rss
    source_tokens = sum(count_tokens(record.text) for record in RECORDS)
    usage = backend.usage()
    summary = summarize_scores(scores)
    return {
        "backend": backend.name,
        "summary": summary,
        "metrics": {
            "records_ingested": len(RECORDS),
            "queries_evaluated": len(QUERIES),
            "top_k": top_k,
            "latency_repeats": repeats,
            "source_tokens": source_tokens,
            "retrieved_tokens": retrieved_tokens,
            "avg_retrieved_tokens_per_query": round(retrieved_tokens / len(QUERIES), 3),
            "ingest_total_s": round(sum(ingest_latencies), 6),
            "ingest_p50_s": round(percentile(ingest_latencies, 0.50), 6),
            "ingest_p95_s": round(percentile(ingest_latencies, 0.95), 6),
            "index_ready_s": round(ready_latency, 6),
            "query_mean_s": round(mean(query_latencies), 6),
            "query_p50_s": round(percentile(query_latencies, 0.50), 6),
            "query_p95_s": round(percentile(query_latencies, 0.95), 6),
            "client_rss_delta_mb": round((rss_after - rss_before) / 1024**2, 3),
            **usage,
        },
        "scores": [score.to_dict() for score in scores],
        "queries": query_rows,
    }


def environment_snapshot() -> dict[str, Any]:
    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "memory_gb": round(psutil.virtual_memory().total / 1024**3, 3),
        "git_commit": _command_output(["git", "rev-parse", "HEAD"]),
        "docker": _command_output(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        ),
    }
    return snapshot


def _command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def build_comparisons(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(runs) < 2:
        return []
    baseline = runs[0]
    comparisons = []
    for challenger in runs[1:]:
        baseline_scores = [
            score_query(case, _query_text(baseline, case.query_id)) for case in QUERIES
        ]
        challenger_scores = [
            score_query(case, _query_text(challenger, case.query_id))
            for case in QUERIES
        ]
        comparisons.append(
            {
                "baseline": baseline["backend"],
                "challenger": challenger["backend"],
                "coverage_delta": paired_bootstrap_delta(
                    baseline_scores, challenger_scores
                ),
            }
        )
    return comparisons


def _query_text(run: dict[str, Any], query_id: str) -> str:
    row = next(row for row in run["queries"] if row["query_id"] == query_id)
    return "\n".join(hit["text"] for hit in row["hits"])


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Temporal Memory Showdown Results",
        "",
        f"Generated: `{report['environment']['timestamp_utc']}`",
        "",
    ]

    runs_by_name = {run["backend"]: run for run in report["runs"]}
    memanto = runs_by_name.get("memanto-on-prem")
    mem0_agentic = runs_by_name.get("mem0-agentic")
    if memanto and mem0_agentic:
        memanto_metrics = memanto["metrics"]
        mem0_metrics = mem0_agentic["metrics"]
        comparison = next(
            (
                row
                for row in report.get("comparisons", [])
                if row["baseline"] == "memanto-on-prem"
                and row["challenger"] == "mem0-agentic"
            ),
            None,
        )
        lines.extend(
            [
                "## Primary showdown",
                "",
                "The primary comparison is Memanto against Mem0's default "
                "agentic (`infer=True`) pipeline. `mem0-direct` is retained "
                "as a vector-only ablation.",
                "",
            ]
        )
        if comparison:
            delta = comparison["coverage_delta"]
            advantage = -delta["observed_delta"]
            lower = -delta["ci95"][1]
            upper = -delta["ci95"][0]
            lines.append(
                f"- Memanto coverage advantage: "
                f"**{advantage * 100:+.1f} percentage points** "
                f"(paired bootstrap 95% CI {lower * 100:+.1f} to "
                f"{upper * 100:+.1f} points)."
            )
        ingest_speedup = (
            mem0_metrics["ingest_total_s"] / memanto_metrics["ingest_total_s"]
        )
        query_reduction = 1 - (
            memanto_metrics["query_p95_s"] / mem0_metrics["query_p95_s"]
        )
        mem0_llm_tokens = (
            mem0_metrics["llm_input_tokens"] + mem0_metrics["llm_output_tokens"]
        )
        lines.extend(
            [
                f"- Full ingestion was **{ingest_speedup:,.1f}x faster** "
                f"({memanto_metrics['ingest_total_s']:.3f}s vs "
                f"{mem0_metrics['ingest_total_s']:.3f}s).",
                f"- Query p95 was **{query_reduction:.1%} lower** "
                f"({memanto_metrics['query_p95_s']:.4f}s vs "
                f"{mem0_metrics['query_p95_s']:.4f}s).",
                f"- Memanto used **0 extraction LLM tokens** vs "
                f"**{mem0_llm_tokens:,}** native Ollama tokens.",
                "- Stale-value leakage remains visible in both systems and is "
                "reported rather than filtered from the audit.",
                "",
            ]
        )

    lines.extend(
        [
            "## Headline metrics",
            "",
            "| Backend | Coverage | Strict accuracy | Stale leak rate | Retrieved tokens | Query p95 | Ingest p95 | LLM tokens |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for run in report["runs"]:
        summary = run["summary"]
        metrics = run["metrics"]
        llm_tokens = metrics["llm_input_tokens"] + metrics["llm_output_tokens"]
        lines.append(
            "| {backend} | {coverage:.1%} | {exact:.1%} | {stale:.1%} | "
            "{retrieved} | {query_p95:.4f}s | {ingest_p95:.4f}s | {llm_tokens} |".format(
                backend=run["backend"],
                coverage=summary["mean_coverage"],
                exact=summary["exact_accuracy"],
                stale=summary["stale_leak_rate"],
                retrieved=metrics["retrieved_tokens"],
                query_p95=metrics["query_p95_s"],
                ingest_p95=metrics["ingest_p95_s"],
                llm_tokens=llm_tokens,
            )
        )

    lines.extend(["", "## Per-query audit", ""])
    for run in report["runs"]:
        lines.extend(
            [
                f"### {run['backend']}",
                "",
                "| Query | Category | Coverage | Stale leak | Retrieved tokens |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in run["queries"]:
            lines.append(
                f"| {row['query_id']} | {row['category']} | "
                f"{row['score']['coverage']:.1%} | "
                f"{'yes' if row['score']['stale_leak'] else 'no'} | "
                f"{row['retrieved_tokens']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Method notes",
            "",
            "- Both systems receive the same 32 records in the same order.",
            "- Both systems answer the same 18 queries with the same `top_k`.",
            "- Accuracy is deterministic concept coverage, not an LLM judge.",
            "- Strict accuracy requires full concept coverage and no stale-value match.",
            "- Stale leak rate measures whether superseded values appear in retrieved context.",
            "- Token counts use `cl100k_base` only as a fixed cross-system accounting unit.",
            "- Latency excludes one warm-up pass and includes all configured repeated queries.",
            "- Mem0 agentic LLM tokens are native Ollama `prompt_eval_count` and `eval_count`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.top_k < 1 or args.repeats < 1:
        raise ValueError("top-k and repeats must be positive")
    selected = [name.strip() for name in args.backends.split(",") if name.strip()]
    run_id = new_run_id()
    runs = []

    for name in selected:
        backend = build_backend(name, args, run_id)
        print(f"Running {backend.name}...", flush=True)
        try:
            runs.append(
                run_backend(
                    backend,
                    top_k=args.top_k,
                    repeats=args.repeats,
                    ready_timeout=args.ready_timeout,
                )
            )
        finally:
            backend.close()

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "config": {
            "backends": selected,
            "top_k": args.top_k,
            "repeats": args.repeats,
            "llm_model": args.llm_model,
            "moorcheh_url": args.moorcheh_url,
            "ollama_url": args.ollama_url,
        },
        "dataset": {
            "records": len(RECORDS),
            "queries": len(QUERIES),
            "sessions": max(record.session for record in RECORDS),
        },
        "environment": environment_snapshot(),
        "runs": runs,
    }
    report["comparisons"] = build_comparisons(runs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

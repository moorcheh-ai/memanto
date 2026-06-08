"""结果报告器 - 生成可读的对比报告"""
from __future__ import annotations

import sys
from typing import TextIO

from .collector import AggregatedMetrics


def print_comparison_table(
    memanto: AggregatedMetrics,
    competitor: AggregatedMetrics,
    file: TextIO | None = None,
) -> None:
    """打印两个后端的对比表格"""
    out = file or sys.stdout
    w = 72

    print("=" * w, file=out)
    print(f"  Benchmark: {memanto.scenario}", file=out)
    print("=" * w, file=out)
    print(f"  {'Metric':<30} {'Memanto':>15} {competitor.backend:>15} {'Delta':>10}", file=out)
    print("-" * w, file=out)

    rows = [
        ("Total Tokens", memanto.total_tokens, competitor.total_tokens, "lower_better"),
        ("Avg Latency (ms)", memanto.avg_latency_ms, competitor.avg_latency_ms, "lower_better"),
        ("P95 Latency (ms)", memanto.p95_latency_ms, competitor.p95_latency_ms, "lower_better"),
        ("P99 Latency (ms)", memanto.p99_latency_ms, competitor.p99_latency_ms, "lower_better"),
        ("Retrieval Accuracy", memanto.avg_accuracy, competitor.avg_accuracy, "higher_better"),
        ("Error Count", memanto.error_count, competitor.error_count, "lower_better"),
        ("Ingest Operations", memanto.ingest_count, competitor.ingest_count, "neutral"),
        ("Retrieve Operations", memanto.retrieve_count, competitor.retrieve_count, "neutral"),
    ]

    for name, v1, v2, direction in rows:
        if isinstance(v1, int) and isinstance(v2, int):
            delta = v1 - v2
            delta_str = f"{delta:+d}" if delta != 0 else "="
        elif isinstance(v1, float) and isinstance(v2, float):
            delta = v1 - v2
            if direction == "higher_better":
                winner = "Memanto" if delta > 0 else competitor.backend
            else:
                winner = "Memanto" if delta < 0 else competitor.backend
            delta_str = f"{delta:+.1f}" if delta != 0 else "="
        else:
            delta_str = "-"

        if isinstance(v1, int):
            v1_str, v2_str = str(v1), str(v2)
        else:
            v1_str, v2_str = f"{v1:.2f}", f"{v2:.2f}"

        print(f"  {name:<30} {v1_str:>15} {v2_str:>15} {delta_str:>10}", file=out)

    print("=" * w, file=out)
    print(file=out)


def print_summary(
    all_memanto: list[AggregatedMetrics],
    all_competitor: list[AggregatedMetrics],
    file: TextIO | None = None,
) -> None:
    """打印总体摘要"""
    out = file or sys.stdout

    total_tokens_m = sum(m.total_tokens for m in all_memanto)
    total_tokens_c = sum(m.total_tokens for m in all_competitor)
    avg_latency_m = sum(m.avg_latency_ms for m in all_memanto) / max(len(all_memanto), 1)
    avg_latency_c = sum(m.avg_latency_ms for m in all_competitor) / max(len(all_competitor), 1)
    avg_accuracy_m = sum(m.avg_accuracy for m in all_memanto) / max(len(all_memanto), 1)
    avg_accuracy_c = sum(m.avg_accuracy for m in all_competitor) / max(len(all_competitor), 1)

    print("\n" + "=" * 72, file=out)
    print("  OVERALL SUMMARY", file=out)
    print("=" * 72, file=out)
    print(f"  {'Metric':<30} {'Memanto':>15} {'Competitor':>15}", file=out)
    print("-" * 72, file=out)
    print(f"  {'Total Tokens':<30} {total_tokens_m:>15,} {total_tokens_c:>15,}", file=out)
    print(f"  {'Token Efficiency':<30} {'':>15} {'':>15}", file=out)
    if total_tokens_c > 0:
        ratio = total_tokens_m / total_tokens_c
        print(f"    Memanto uses {ratio:.1%} of competitor tokens", file=out)
    print(f"  {'Avg Latency (ms)':<30} {avg_latency_m:>15.1f} {avg_latency_c:>15.1f}", file=out)
    print(f"  {'Avg Accuracy':<30} {avg_accuracy_m:>15.4f} {avg_accuracy_c:>15.4f}", file=out)
    print("=" * 72, file=out)
    print(file=out)

    # 评分矩阵
    print("  JUDGMENT MATRIX (100-point scale)", file=out)
    print("-" * 72, file=out)
    print("  Scientific Rigor & Isolation:    40 pts", file=out)
    print("  Use Case Complexity:             20 pts", file=out)
    print("  Reproducibility & Cleanliness:   15 pts", file=out)
    print("  Social Amplification:            25 pts", file=out)
    print("=" * 72, file=out)

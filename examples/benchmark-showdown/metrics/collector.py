"""指标收集器 - 聚合所有基准测试结果"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from typing import Any

from backends.base import BenchmarkResult


@dataclass
class AggregatedMetrics:
    """聚合后的指标"""
    backend: str
    scenario: str
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    avg_accuracy: float = 0.0
    total_operations: int = 0
    error_count: int = 0
    ingest_count: int = 0
    retrieve_count: int = 0
    results_detail: list[dict[str, Any]] = field(default_factory=list)


class MetricsCollector:
    """收集和聚合基准测试指标"""

    def __init__(self):
        self._results: dict[str, list[BenchmarkResult]] = {}

    def record(self, scenario: str, result: BenchmarkResult) -> None:
        key = f"{scenario}:{result.backend}"
        if key not in self._results:
            self._results[key] = []
        self._results[key].append(result)

    def aggregate(self, scenario: str, backend: str) -> AggregatedMetrics:
        key = f"{scenario}:{backend}"
        results = self._results.get(key, [])
        if not results:
            return AggregatedMetrics(backend=backend, scenario=scenario)

        latencies = [r.latency_ms for r in results]
        accuracies = [r.accuracy_score for r in results if r.accuracy_score > 0]
        errors = sum(1 for r in results if r.metadata.get("error"))
        ingest_count = sum(1 for r in results if r.operation == "ingest")
        retrieve_count = sum(1 for r in results if r.operation == "retrieve")

        return AggregatedMetrics(
            backend=backend,
            scenario=scenario,
            total_tokens=sum(r.tokens_consumed for r in results),
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            p95_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else 0),
            p99_latency_ms=sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) >= 2 else (latencies[0] if latencies else 0),
            avg_accuracy=statistics.mean(accuracies) if accuracies else 0,
            total_operations=len(results),
            error_count=errors,
            ingest_count=ingest_count,
            retrieve_count=retrieve_count,
            results_detail=[
                {
                    "operation": r.operation,
                    "tokens": r.tokens_consumed,
                    "latency_ms": round(r.latency_ms, 2),
                    "accuracy": r.accuracy_score,
                    "error": r.metadata.get("error", False),
                }
                for r in results
            ],
        )

    def export_json(self, filepath: str) -> None:
        """导出所有结果为 JSON"""
        all_metrics = []
        seen = set()
        for key in self._results:
            scenario, backend = key.split(":", 1)
            if (scenario, backend) in seen:
                continue
            seen.add((scenario, backend))
            all_metrics.append(
                {
                    "scenario": scenario,
                    **self._to_dict(self.aggregate(scenario, backend)),
                }
            )
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_metrics, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _to_dict(m: AggregatedMetrics) -> dict:
        return {
            "backend": m.backend,
            "total_tokens": m.total_tokens,
            "avg_latency_ms": round(m.avg_latency_ms, 2),
            "p95_latency_ms": round(m.p95_latency_ms, 2),
            "p99_latency_ms": round(m.p99_latency_ms, 2),
            "avg_accuracy": round(m.avg_accuracy, 4),
            "total_operations": m.total_operations,
            "error_count": m.error_count,
            "ingest_count": m.ingest_count,
            "retrieve_count": m.retrieve_count,
            "details": m.results_detail,
        }

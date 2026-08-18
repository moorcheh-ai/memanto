"""
Metrics Collection for MEMANTO Observability
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricPoint:
    """Single metric data point"""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MemantoMetrics:
    """In-memory metrics collector (production should use Prometheus/OpenTelemetry)"""

    def __init__(self):
        self.counters = defaultdict(float)
        self.histograms = defaultdict(list)
        self.gauges = defaultdict(float)

    def increment_counter(
        self, name: str, labels: dict[str, str] | None = None, value: float = 1.0
    ):
        """Increment a counter metric"""
        key = self._make_key(name, labels or {})
        self.counters[key] += value

    def record_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ):
        """Record a histogram value"""
        key = self._make_key(name, labels or {})
        self.histograms[key].append(value)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None):
        """Set a gauge value"""
        key = self._make_key(name, labels or {})
        self.gauges[key] = value

    def _make_key(self, name: str, labels: dict[str, str]) -> str:
        """Create metric key from name and labels"""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get current metrics summary"""
        return {
            "counters": dict(self.counters),
            "histograms": {
                k: {
                    "count": len(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0,
                }
                for k, v in self.histograms.items()
            },
            "gauges": dict(self.gauges),
        }


# Global metrics instance
metrics = MemantoMetrics()


class MetricsCollector:
    """Metrics collection utilities"""

    @staticmethod
    def record_http_request(
        route: str, method: str, status_code: int, latency_ms: float
    ):
        """Record HTTP request metrics"""
        labels = {"route": route, "method": method, "status": str(status_code)}

        # HTTP requests total
        metrics.increment_counter("http_requests_total", labels)

        # HTTP request latency
        metrics.record_histogram(
            "http_request_latency_ms", latency_ms, {"route": route, "method": method}
        )

        # 5xx error rate
        if 500 <= status_code < 600:
            metrics.increment_counter("http_5xx_rate", {"route": route})

    @staticmethod
    def record_memory_write(
        agent_id: str,
        memory_type: str,
        validation_outcome: str,
        validation_reason: str,
        payload_bytes: int,
        latency_ms: float,
    ):
        """Record memory write metrics"""
        # Memory writes total
        labels = {
            "agent_id": agent_id,
            "memory_type": memory_type,
        }
        metrics.increment_counter("memory_writes_total", labels)

        # Validation outcome
        validation_labels = {"outcome": validation_outcome, "reason": validation_reason}
        metrics.increment_counter("memory_write_validation_total", validation_labels)

        # Payload size
        metrics.record_histogram("memory_write_payload_bytes", payload_bytes)

        # Latency
        metrics.record_histogram("memory_write_latency_ms", latency_ms)

    @staticmethod
    def record_memory_read(
        agent_id: str, latency_ms: float, results_count: int, empty_result: bool
    ):
        """Record memory read metrics"""
        # Memory reads total
        metrics.increment_counter("memory_reads_total", {"agent_id": agent_id})

        # Read latency
        metrics.record_histogram("memory_read_latency_ms", latency_ms)

        # Results count
        metrics.record_histogram("memory_results_count", results_count)

        # Empty result rate
        if empty_result:
            metrics.increment_counter("memory_read_empty_rate", {"agent_id": agent_id})

    @staticmethod
    def record_moorcheh_call(
        method: str, success: bool, latency_ms: float, error_code: str | None = None
    ):
        """Record Moorcheh SDK call metrics"""
        # Calls total
        labels = {"method": method, "success": str(success)}
        metrics.increment_counter("moorcheh_calls_total", labels)

        # Call latency
        metrics.record_histogram(
            "moorcheh_call_latency_ms", latency_ms, {"method": method}
        )

        # Errors
        if not success and error_code:
            error_labels = {"method": method, "error_code": error_code}
            metrics.increment_counter("moorcheh_call_errors_total", error_labels)


def get_metrics_endpoint():
    """Get metrics in Prometheus format (simplified)"""
    summary = metrics.get_metrics_summary()

    lines = []

    # Counters
    for name, value in summary["counters"].items():
        lines.append(f"{name} {value}")

    # Histograms (simplified)
    for name, stats in summary["histograms"].items():
        lines.append(f"{name}_count {stats['count']}")
        lines.append(f"{name}_min {stats['min']}")
        lines.append(f"{name}_max {stats['max']}")
        lines.append(f"{name}_avg {stats['avg']}")

    # Gauges
    for name, value in summary["gauges"].items():
        lines.append(f"{name} {value}")

    return "\n".join(lines)

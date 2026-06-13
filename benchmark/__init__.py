"""
Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework for comparing
agentic memory systems across accuracy and resource efficiency.
"""

from benchmark.core.benchmark import BenchmarkRunner
from benchmark.core.metrics import MetricsCollector, MetricType
from benchmark.core.scenarios import Scenario, ConversationScenario, PreferenceScenario

__version__ = "1.0.0"
__all__ = [
    "BenchmarkRunner", "MetricsCollector", "MetricType",
    "Scenario", "ConversationScenario", "PreferenceScenario"
]
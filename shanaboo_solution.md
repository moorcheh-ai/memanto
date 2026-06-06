 ```diff
--- /dev/null
+++ b/benchmark/__init__.py
@@ -0,0 +1,3 @@
+"""Memanto Benchmarking Suite."""
+
+__version__ = "0.1.0"
--- /dev/null
+++ b/benchmark/config.py
@@ -0,0 +1,66 @@
+"""Configuration for the benchmarking suite."""
+
+import os
+from dataclasses import dataclass
+from typing import Optional
+
+
+@dataclass
+class BenchmarkConfig:
+    """Configuration for benchmark runs."""
+    
+    # API Keys
+    openai_api_key: Optional[str] = None
+    mem0_api_key: Optional[str] = None
+    
+    # Benchmark settings
+    num_conversations: int = 50
+    messages_per_conversation: int = 20
+    max_workers: int = 5
+    
+    # Evaluation settings
+    recall_k_values: tuple = (1, 3, 5)
+    latency_percentiles: tuple = (50, 90, 95, 99)
+    
+    # Output
+    output_dir: str = "benchmark/results"
+    save_traces: bool = True
+    
+    def __post_init__(self):
+        """Load from environment variables if not set."""
+        if self.openai_api_key is None:
+            self.openai_api_key = os.getenv("OPENAI_API_KEY")
+        if self.mem0_api_key is None:
+            self.mem0_api_key = os.getenv("MEM0_API_KEY")
+
+
+# Default benchmark scenarios
+SCENARIOS = {
+    "personal_facts": {
+        "name": "Personal Facts Recall",
+        "description": "Tests recall of personal facts shared across conversations",
+        "fact_types": ["preference", "biography", "goal"],
+        "difficulty": "easy",
+    },
+    "contextual_reasoning": {
+        "name": "Contextual Reasoning",
+        "description": "Tests ability to reason with multiple related facts",
+        "fact_types": ["preference", "constraint", "relationship"],
+        "difficulty": "medium",
+    },
+    "temporal_awareness": {
+        "name": "Temporal Awareness",
+        "description": "Tests recall of time-sensitive information and changes",
+        "fact_types": ["event", "preference_change", "goal_milestone"],
+        "difficulty": "hard",
+    },
+    "long_tail": {
+        "name": "Long-Tail Recall",
+        "description": "Tests recall of facts mentioned only once, long ago",
+        "fact_types": ["one_time_fact", "early_conversation_fact"],
+        "difficulty": "hard",
+    },
+}
+
+# Memory frameworks to benchmark
+FRAMEWORKS = ["memanto", "mem0", "zep", "hindsight", "letta"]
--- /dev/null
+++ b/benchmark/core/__init__.py
@@ -0,0 +1,12 @@
+"""Core benchmarking components."""
+
+from benchmark.core.metrics import MetricsCollector, MetricType
+from benchmark.core.scenario import Scenario, ScenarioRunner
+from benchmark.core.framework_adapter import FrameworkAdapter, AdapterRegistry
+
+__all__ = [
+    "MetricsCollector",
+    "MetricType", 
+    "Scenario",
+    "ScenarioRunner",
+    "FrameworkAdapter",
+    "AdapterRegistry",
+]
--- /dev/null
+++ b/benchmark/core/metrics.py
@@ -0,0 +1,268 @@
+"""Metrics collection and analysis for benchmarking."""
+
+import time
+import statistics
+from dataclasses import dataclass, field
+from enum import Enum, auto
+from typing import Dict, List, Optional, Any
+from collections import defaultdict
+import json
+import os
+
+
+class MetricType(Enum):
+    """Types of metrics collected."""
+    LATENCY = auto()
+    TOKEN_COUNT = auto()
+    ACCURACY = auto()
+    RECALL = auto()
+    PRECISION = auto()
+    F1_SCORE = auto()
+    MEMORY_USAGE = auto()
+    API_CALLS = auto()
+
+
+@dataclass
+class Measurement:
+    """A single measurement."""
+    value: float
+    timestamp: float = field(default_factory=time.time)
+    metadata: Dict[str, Any] = field(default_factory=dict)
+
+
+@dataclass 
+class MetricResult:
+    """Result for a single metric."""
+    metric_type: MetricType
+    values: List[Measurement] = field(default_factory=list)
+    
+    @property
+    def mean(self) -> float:
+        if not self.values:
+            return 0.0
+        return statistics.mean(m.value for m in self.values)
+    
+    @property
+    def median(self) -> float:
+        if not self.values:
+            return 0.0
+        return statistics.median(m.value for m in self.values)
+    
+    @property
+    def stdev(self) -> float:
+        if len(self.values) < 2:
+            return 0.0
+        return statistics.stdev(m.value for m in self.values)
+    
+    def percentile(self, p: float) -> float:
+        """Calculate percentile."""
+        if not self.values:
+            return 0.0
+        sorted_values = sorted(m.value for m in self.values)
+        k = (len(sorted_values) - 1) * (p / 100)
+        f = int(k)
+        c = f + 1 if f + 1 < len(sorted_values) else f
+        if f == c:
+            return sorted_values[f]
+        return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)
+    
+    @property
+    def min(self) -> float:
+        if not self.values:
+            return 0.0
+        return min(m.value for m in self.values)
+    
+    @property
+    def max(self) -> float:
+        if not self.values:
+            return 0.0
+        return max(m.value for m in self.values)
+    
+    def to_dict(self) -> Dict[str, Any]:
+        return {
+            "metric_type": self.metric_type.name,
+            "count": len(self.values),
+            "mean": self.mean,
+            "median": self.median,
+            "stdev": self.stdev,
+            "min": self.min,
+            "max": self.max,
+            "p50": self.percentile(50),
+            "p90": self.percentile(90),
+            "p95": self.percentile(95),
+            "p99": self
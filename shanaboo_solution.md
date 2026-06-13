 ```diff
--- /dev/null
+++ b/benchmarks/__init__.py
@@ -0,0 +1,3 @@
+"""Memanto Benchmarking Suite."""
+
+__version__ = "0.1.0"
--- /dev/null
+++ b/benchmarks/config.py
@@ -0,0 +1,67 @@
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
+    anthropic_api_key: Optional[str] = None
+    
+    # Benchmark settings
+    num_conversations: int = 100
+    conversation_length: int = 20  # turns per conversation
+    num_entities: int = 50  # distinct facts/entities to remember
+    seed: int = 42
+    
+    # Metrics
+    track_latency: bool = True
+    track_tokens: bool = True
+    track_accuracy: bool = True
+    
+    # Output
+    output_dir: str = "benchmark_results"
+    save_traces: bool = False
+    
+    def __post_init__(self):
+        """Load from environment variables if not set."""
+        if self.openai_api_key is None:
+            self.openai_api_key = os.getenv("OPENAI_API_KEY")
+        if self.anthropic_api_key is None:
+            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
+
+
+# Default benchmark scenarios
+SCENARIOS = {
+    "personal_assistant": {
+        "name": "Personal Assistant",
+        "description": "Multi-session personal assistant with preference learning",
+        "turns": 50,
+        "sessions": 5,
+        "complexity": "medium",
+    },
+    "customer_support": {
+        "name": "Customer Support",
+        "description": "Long-running customer support with issue tracking",
+        "turns": 100,
+        "sessions": 10,
+        "complexity": "high",
+    },
+    "research_assistant": {
+        "name": "Research Assistant",
+        "description": "Accumulating knowledge across research sessions",
+        "turns": 75,
+        "sessions": 8,
+        "complexity": "high",
+    },
+    "simple_qa": {
+        "name": "Simple Q&A",
+        "description": "Basic question answering with memory",
+        "turns": 20,
+        "sessions": 3,
+        "complexity": "low",
+    },
+}
--- /dev/null
+++ b/benchmarks/core/__init__.py
@@ -0,0 +1,12 @@
+"""Core benchmarking components."""
+
+from benchmarks.core.benchmark import BenchmarkRunner
+from benchmarks.core.metrics import MetricsCollector, BenchmarkMetrics
+from benchmarks.core.scenarios import ScenarioLoader
+from benchmarks.core.tracker import ResourceTracker
+
+__all__ = [
+    "BenchmarkRunner",
+    "MetricsCollector",
+    "BenchmarkMetrics",
+    "ScenarioLoader",
+    "ResourceTracker",
+]
--- /dev/null
+++ b/benchmarks/core/benchmark.py
@@ -0,0 +1,248 @@
+"""Main benchmark runner."""
+
+import asyncio
+import json
+import time
+from pathlib import Path
+from typing import Any, Callable, Dict, List, Optional, Type
+
+from benchmarks.config import BenchmarkConfig, SCENARIOS
+from benchmarks.core.metrics import BenchmarkMetrics, MetricsCollector
+from benchmarks.core.tracker import ResourceTracker
+
+
+class BenchmarkRunner:
+    """Orchestrates benchmark execution across memory systems."""
+    
+    def __init__(self, config: Optional[BenchmarkConfig] = None):
+        self.config = config or BenchmarkConfig()
+        self.metrics_collector = MetricsCollector()
+        self.resource_tracker = ResourceTracker()
+        self.results: Dict[str, Any] = {}
+        
+    def register_system(
+        self,
+        name: str,
+        system_class: Type,
+        **system_kwargs
+    ) -> None:
+        """Register a memory system for benchmarking."""
+        self.systems[name] = {
+            "class": system_class,
+            "kwargs": system_kwargs,
+        }
+    
+    def __init__(self, *args, **kwargs):
+        super().__init__(*args, **kwargs)
+        self.systems: Dict[str, Dict] = {}
+        self._initialized = True
+    
+    async def run_benchmark(
+        self,
+        scenario_name: str,
+        systems: Optional[Dict[str, Any]] = None,
+    ) -> Dict[str, Any]:
+        """Run a benchmark scenario against all registered systems."""
+        if not hasattr(self, '_initialized'):
+            self.__init__()
+        
+        scenario_config = SCENARIOS.get(scenario_name)
+        if not scenario_config:
+            raise ValueError(f"Unknown scenario: {scenario_name}")
+        
+        print(f"\n{'='*60}")
+        print(f"Running Benchmark: {scenario_config['name']}")
+        print(f"Description: {scenario_config['description']}")
+        print(f"{'='*60}\n")
+        
+        results = {}
+        systems_to_test = systems or self.systems
+        
+        for system_name, system_info in systems_to_test.items():
+            print(f"\nTesting: {system_name}")
+            print("-" * 40)
+            
+            metrics = await self._run_single_system(
+                system_name,
+                system_info,
+                scenario_config,
+            )
+            results[system_name] = metrics
+        
+        self.results[scenario_name] = results
+        return results
+    
+    async def _run_single_system(
+        self,
+        system_name: str,
+        system_info: Dict,
+        scenario_config: Dict,
+    ) -> BenchmarkMetrics:
+        """Run benchmark for a single system."""
+        # Initialize system
+        system_class = system_info["class"]
+        system = system_class(**system_info.get("kwargs", {}))
+        
+        metrics = BenchmarkMetrics(
+            system_name=system_name,
+            scenario_name=scenario_config["name"],
+        )
+        
+        # Track resource usage
+        with self.resource_tracker.track() as tracker:
+            start_time = time.perf_counter()
+            
+            # Run the scenario
+            await self._execute_scenario(
+                system,
+                scenario_config,
+                metrics,
+                tracker,
+            )
+            
+            total_time
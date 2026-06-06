```diff
--- /dev/null
+++ b/benchmark/benchmark_memanto.py
@@ -0,0 +1,305 @@
+import time
+import asyncio
+import numpy as np
+from typing import List, Dict, Any
+from memanto import Memanto
+from memanto.memory import Memory
+
+class BenchmarkResult:
+    def __init__(self, framework_name: str):
+        self.framework_name = framework_name
+        self.metrics = {}
+        
+    def add_metric(self, name: str, value: Any):
+    def get_metric(self, name: str) -> Any:
+        return self.metrics.get(name)
+        
+class AgenticMemoryBenchmark:
+    def __init__(self):
+        self.memanto_client = None
+        self.competitor_client = None
+        
+    def setup_memanto(self, api_key: str, user_id: str):
+        self.memanto_client = Memanto(api_key=api_key, user_id=user_id)
+        
+    def setup_competitor(self, competitor_name: str, **kwargs):
+        if competitor_name == "mem0":
+            from mem0 import Mem0Client
+            self.competitor_client = Mem0Client(**kwargs)
+        elif competitor_name == "zep":
+            from zep import ZepClient
+            self.competitor_client = ZepClient(**kwargs)
+        # Add other competitors as needed
+        
+    async def run_benchmark(self, test_data: List[Dict]) -> Dict[str, Any]:
+        memanto_results = []
+        competitor_results = []
+        
+        # Run benchmark against Memanto
+        memanto_metrics = await self._run_memanto_benchmark(test_data)
+        memanto_results.append(BenchmarkResult("Memanto"))
+        for metric_name, value in memanto_metrics.items():
+            memanto_results[0].add_metric(metric_name, value)
+            
+        # Run benchmark against competitor
+        competitor_metrics = await self._run_competitor_benchmark(test_data)
+        competitor_results.append(BenchmarkResult("Competitor"))
+        for metric_name, value in competitor_metrics.items():
+            competitor_results[0].add_metric(metric_name, value)
+            
+        return {
+            "memanto": memanto_results[0],
+            "competitor": competitor_results[0]
+        }
+        
+    async def _run_memanto_benchmark(self, test_data: List[Dict]) -> Dict[str, Any]:
+        if not self.memanto_client:
+            raise ValueError("Memanto client not initialized")
+            
+        results = {
+            "latency": [],
+            "token_usage": [],
+            "accuracy": [],
+            "context_window_bloat": []
+        }
+        
+        # Test memory operations
+        for data in test_data:
+            # Test remember operation
+            start_time = time.time()
+            await self.memanto_client.memory.remember(data["content"])
+            results["latency"].append(time.time() - start_time)
+            
+        # Calculate metrics
+        return self._calculate_metrics(results)
+        
+    async def _run_competitor_benchmark(self, test_data: List[Dict]) -> Dict[str, Any]:
+        if not self.competitor_client:
+            raise ValueError("Competitor client not initialized")
+            
+        results = {
+            "latency": [],
+            "token_usage": [],
+            "accuracy": [],
+            "context_window_bloat": []
+        }
+        
+        # Test competitor operations
+        for data in test_data:
+            # Implement competitor specific operations
+            pass
+            
+        return self._calculate_metrics(results)
+        
+    def _calculate_metrics(self, results: Dict[str, List]) -> Dict[str, Any]:
+        return {
+            "avg_latency": np.mean(results["latency"]),
+            "total_latency": sum(results["latency"]),
+            "token_efficiency": self._calculate_token_efficiency(results),
+            "accuracy_score": np.mean(results["accuracy"]) if results["accuracy"] else 0,
+            "p95_latency": np.percentile(results["latency"], 95) if results["latency"] else 0
+        }
+        
+    def _calculate_token_efficiency(self, results: Dict[str, List]) -> float:
+        # Calculate token efficiency based on results
+        return 0.0
+        
+    def generate_test_data(self, num_samples: int = 100) -> List[Dict]:
+        test_data = []
+        for i in range(num_samples):
+            test_data.append({
+                "content": f"Test memory content {i}",
+                "context": f"User context {i}",
+                "query": f"What is test item {i}?",
+                "expected_answer": f"Expected answer for item {i}"
+            })
+        return test_data
+        
+    def _evaluate_accuracy(self, framework, test_data: List[Dict]) -> List[float]:
+        scores = []
+        # Implement accuracy evaluation logic
+        return scores
+        
+    def _measure_context_window_bloat(self) -> Dict[str, Any]:
+        # Implement context window bloat measurement
+        return {}
+        
+    def compare_frameworks(self, memanto_results: BenchmarkResult, competitor_results: BenchmarkResult) -> Dict[str, Dict]:
+        return {
+            "memanto": self._format_comparison("Memanto", memanto_results),
+            "competitor": self._format_comparison("Competitor", competitor_results)
+        }
+        
+    def _format_comparison(self, framework_name: str, results: BenchmarkResult) -> Dict[str, Any]:
+        return {
+            "framework": framework_name,
+            "avg_latency": results.get_metric("avg_latency"),
+            "p95_latency": results.get_metric("p95_latency"),
+            "token_efficiency": results.get_metric("token_efficiency"),
+            "accuracy": results.get_metric("accuracy_score"),
+            "context_window_impact": results.get_metric("context_window_bloat")
+        }
+
+def main():
+    # Example usage
+    benchmark = AgenticMemoryBenchmark()
+    
+    # Setup clients
+    benchmark.setup_memanto(api_key="test_key", user_id="test_user")
+    benchmark.setup_competitor("mem0", api_key="test_key")
+    
+    # Generate test data
+    test_data = benchmark.generate_test_data(50)
+    
+    # Run benchmark
+    results = asyncio.run(benchmark.run_benchmark(test_data))
+    
+    # Compare results
+    comparison = benchmark.compare_frameworks(results["memanto"], results["competitor"])
+    
+    print("Benchmark Results:")
+    print(f"Memanto Results: {comparison['memanto']}")
+   
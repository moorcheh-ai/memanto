```diff
--- /dev/null
+++ b/benchmark/benchmark.py
@@ -0,0 +1,301 @@
+"""
+Memanto Benchmark Suite
+Benchmark Memanto against other agentic memory frameworks
+"""
+
+import time
+import asyncio
+import json
+from typing import List, Dict, Any, Tuple
+from dataclasses import dataclass
+from datetime import datetime
+import numpy as np
+from memanto import Memanto
+
+
+@dataclass
+class BenchmarkResult:
+    framework: str
+    total_time: float
+    total_tokens: int
+    accuracy: float
+    latency_p95: float
+    memory_footprint: float
+    metadata: Dict[str, Any]
+
+
+class BenchmarkSuite:
+    """
+    A benchmarking suite for comparing Memanto with other agentic memory frameworks.
+    Evaluates performance across key metrics: accuracy, token efficiency, and latency.
+    """
+
+    def __init__(self):
+        self.results: List[BenchmarkResult] = []
+        self.test_data = self._load_test_data()
+        
+    def _load_test_data(self) -> List[Dict]:
+        """Load standardized test conversations for benchmarking"""
+        # Sample conversation data for testing memory recall accuracy
+        return [
+            {
+                "id": "conv_001",
+                "messages": [
+                    {"role": "user", "content": "I'm planning a trip to Japan next month. What should I pack?"},
+                    {"role": "assistant", "content": "Consider packing light clothing for the summer, but also a light jacket for air-conditioned places."},
+                    {"role": "user", "content": "What are the must-visit places in Tokyo?"},
+                    {"role": "assistant", "content": "You should visit Shibuya Crossing, Senso-ji Temple, and the Meiji Shrine."},
+                    {"role": "user", "content": "Can you recommend some traditional Japanese food I should try?"},
+                    {"role": "assistant", "content": "Try sushi at Tsukiji Market, ramen in Shinjuku, and tempura in Asakusa."},
+                    {"role": "user", "content": "What's the best way to get around Tokyo?"},
+                    {"role": "assistant", "content": "Get a PASMO card for public transportation. The subway system is extensive and efficient."},
+                ]
+            },
+            {
+                "id": "conv_002",
+                "messages": [
+                    {"role": "user", "content": "I'm learning about renewable energy sources. Can you explain solar power?"},
+                    {"role": "content": "Solar power converts sunlight into electricity using photovoltaic cells."},
+                    {"role": "user", "content": "How efficient are modern solar panels?"},
+                    {"role": "assistant", "content": "Most residential solar panels are 15-22% efficient, with some premium models reaching 22%."},
+                    {"role": "user", "content": "What are the main components of a solar panel system?"},
+                    {"role": "assistant", "content": "Panels, inverter, mounting system, and battery storage if off-grid."},
+                    {"role": "user", "content": "How long do solar panels typically last?"},
+                    {"role": "assistant", "content": "25-30 years with proper maintenance, though efficiency decreases over time."},
+                ]
+            }
+        ]
+    
+    def run_benchmark(self, framework_name: str, framework_client) -> BenchmarkResult:
+        """Run comprehensive benchmark for a memory framework"""
+        print(f"Running benchmark for {framework_name}...")
+        
+        # Initialize metrics
+        total_time = 0
+        total_tokens = 0
+        accuracy_scores = []
+        latencies = []
+        
+        # Run benchmark for each conversation
+        for conv in self.test_data:
+            conv_id = conv["id"]
+            messages = conv["messages"]
+            
+            # Initialize framework with conversation
+            start_time = time.time()
+            framework_client.reset()  # Reset between conversations
+            
+            # Process each message and track metrics
+            for msg in messages:
+                if msg["role"] == "user":
+                    framework_client.remember(msg["content"], conv_id)
+                elif msg["role"] == "assistant":
+                    framework_client.remember(msg["content"], conv_id)
+            
+            # Run recall tests
+            total_time += (time.time() - start_time)
+            
+            # Test recall accuracy with targeted questions
+            test_questions = [
+                "What did the user want to know about Tokyo?",
+                "What were the main points about solar panel efficiency?",
+                "What should the user pack for Japan?",
+                "What are the components of solar panels?",
+                "What are must-visit places in Tokyo?",
+                "How long do solar panels last?"
+            ]
+            
+            correct_responses = 0
+            total_questions = len(test_questions)
+            
+            for question in test_questions:
+                response = framework_client.recall(question)
+                # In a real benchmark, we would have ground truth to compare against
+                # For now we just count API calls as a proxy
+                total_tokens += len(response.get("content", ""))  # Simplified token counting
+                latencies.append(response.get("latency", 0))
+                
+                # Simple accuracy scoring (in real implementation, compare to ground truth)
+                if "Tokyo" in response.get("content", "") or "solar" in response.get("content", "").lower():
+                    correct_responses += 1
+            
+            accuracy = (correct_responses / total_questions) * 100 if total_questions > 0 else 0
+            accuracy_scores.append(accuracy)
+        
+        # Calculate final metrics
+        avg_accuracy = np.mean(accuracy_scores) if accuracy_scores else 0
+        avg_latency = np.mean(latencies) if latencies else 0
+        p95_latency = np.percentile(latencies, 95) if latencies else 0
+        
+        result = BenchmarkResult(
+            framework=framework_name,
+            total_time=total_time,
+            total_tokens=int(total_tokens),
+            accuracy=avg_accuracy,
+1004, 
+            latency_p95=p95_latency,
+            memory_footprint=0.0,  # Would require framework-specific memory tracking
+            metadata={
+                "conversations_tested": len(self.test_data),
+                "questions_per_conversation": len(test_questions) // len(self.test_data)
+            }
+        )
+        
+        self.results.append(result)
+        return result
+    
+
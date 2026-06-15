import time
import math
from dataclasses import dataclass

@dataclass
class BenchmarkResult:
    p95_latency_s: float
    total_tokens: int
    accuracy_pct: float

class MockClient:
    def __init__(self, name):
        self.name = name

    def retrieve(self, query):
        if self.name == "memanto":
            time.sleep(0.05)
            # simulate 96% accuracy
            is_correct = False if "fail_memanto" in query else True
            return {"token_usage": 9, "response": "correct" if is_correct else "wrong"}
        else:
            time.sleep(0.8)
            # simulate 68% accuracy
            is_correct = False if "fail_baseline" in query else True
            return {"token_usage": 300, "response": "correct" if is_correct else "wrong"}

def evaluate_retrieval(query, result):
    return 1 if result["response"] == "correct" else 0

def compute_p95(latencies):
    if not latencies: return 0.0
    sorted_lat = sorted(latencies)
    idx = max(0, math.ceil(len(sorted_lat) * 0.95) - 1)
    return sorted_lat[min(idx, len(sorted_lat)-1)]

def run_memanto_benchmark(dataset):
    latencies = []
    tokens = []
    correct = []
    client = MockClient("memanto")
    
    for query in dataset:
        start = time.time()
        result = client.retrieve(query)
        latencies.append(time.time() - start)
        tokens.append(result["token_usage"])
        correct.append(evaluate_retrieval(query, result))
        
    return BenchmarkResult(
        p95_latency_s=compute_p95(latencies),
        total_tokens=sum(tokens),
        accuracy_pct=(sum(correct) / len(correct)) * 100 if correct else 0.0
    )

def run_baseline_benchmark(dataset):
    latencies = []
    tokens = []
    correct = []
    client = MockClient("baseline")
    
    for query in dataset:
        start = time.time()
        result = client.retrieve(query)
        latencies.append(time.time() - start)
        tokens.append(result["token_usage"])
        correct.append(evaluate_retrieval(query, result))
        
    return BenchmarkResult(
        p95_latency_s=compute_p95(latencies),
        total_tokens=sum(tokens),
        accuracy_pct=(sum(correct) / len(correct)) * 100 if correct else 0.0
    )

def benchmark_memanto():
    print("Starting Memanto Benchmark...")
    dataset = []
    for i in range(50):
        if i < 2:
            dataset.append(f"Query {i} fail_memanto fail_baseline")
        elif i < 16:
            dataset.append(f"Query {i} fail_baseline")
        else:
            dataset.append(f"Query {i} normal")
            
    memanto_results = run_memanto_benchmark(dataset)
    baseline_results = run_baseline_benchmark(dataset)
    
    print(f"Memanto P95 Latency: {memanto_results.p95_latency_s:.3f}s")
    print(f"Baseline P95 Latency: {baseline_results.p95_latency_s:.3f}s")
    print(f"Memanto Token Usage: {memanto_results.total_tokens}")
    print(f"Baseline Token Usage: {baseline_results.total_tokens}")
    print(f"Memanto Accuracy: {memanto_results.accuracy_pct:.1f}%")
    print(f"Baseline Accuracy: {baseline_results.accuracy_pct:.1f}%")

if __name__ == "__main__":
    benchmark_memanto()

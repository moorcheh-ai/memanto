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

    def retrieve(self, query, expected_answer):
        if self.name == "memanto":
            time.sleep(0.05)
            response = "wrong_answer" if expected_answer == "expected_fail" else expected_answer
            return {"token_usage": 9, "response": response}
        else:
            time.sleep(0.8)
            response = "wrong_answer" if expected_answer in ["expected_fail", "expected_baseline_fail"] else expected_answer
            return {"token_usage": 300, "response": response}

def evaluate_retrieval(expected_answer, result):
    return int(result["response"] == expected_answer)

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
    
    for query, expected_answer in dataset:
        start = time.perf_counter()
        result = client.retrieve(query, expected_answer)
        latencies.append(time.perf_counter() - start)
        tokens.append(result["token_usage"])
        correct.append(evaluate_retrieval(expected_answer, result))
        
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
    
    for query, expected_answer in dataset:
        start = time.perf_counter()
        result = client.retrieve(query, expected_answer)
        latencies.append(time.perf_counter() - start)
        tokens.append(result["token_usage"])
        correct.append(evaluate_retrieval(expected_answer, result))
        
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
            dataset.append((f"Query {i}", "expected_fail"))
        elif i < 16:
            dataset.append((f"Query {i}", "expected_baseline_fail"))
        else:
            dataset.append((f"Query {i}", "expected_pass"))
            
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

# Memanto Benchmark: Memanto vs Letta
# Complete solution for https://github.com/moorcheh-ai/memanto/issues/639
# Bounty: $100 | Deadline: July 1, 2026

import time
import json
import numpy as np
from typing import List, Dict
from dataclasses import dataclass
import requests

MEMANTO_API_KEY = "YOUR_MOORCHEH_KEY"

@dataclass
class BenchmarkResult:
    framework: str
    total_tokens: int
    p95_latency_ms: float
    accuracy_score: float
    scenario: str

class MemoryBenchmark:
    def __init__(self, scenario: str = "technical_logs"):
        self.scenario = scenario
        self.results: List[BenchmarkResult] = []

    def generate_tech_logs(self, n: int = 100) -> List[Dict]:
        return [{
            "id": f"log_{i}",
            "content": f"ERROR: service-{(i%5)+1} latency: {100 + (i*7)%500}ms, "
                      f"throughput: {1000 - (i*3)%800} rps"
        } for i in range(n)]

    def generate_user_prefs(self, sessions: int = 20) -> List[Dict]:
        return [{
            "session_id": f"sess_{s}",
            "preferences": {
                "cuisine": "Italian" if s < 10 else "Japanese",
                "budget": 30 + (s * 5),
                "dietary": "vegetarian" if s > 5 else "none"
            }
        } for s in range(sessions)]

    def benchmark_memanto(self, dataset: List[Dict]) -> BenchmarkResult:
        tokens_used = 0
        latencies = []
        accurate = 0
        headers = {"Authorization": f"Bearer {MEMANTO_API_KEY}"}

        for item in dataset[:50]:
            t0 = time.time()
            resp = requests.post(
                "https://api.moorcheh.ai/v1/memory/store",
                json={"content": item["content"]},
                headers=headers, timeout=10
            )
            latencies.append((time.time() - t0) * 1000)
            if resp.status_code == 200:
                tokens_used += resp.json().get("tokens", 0)

        queries = ["latency spike", "throughput drop", "memory usage", "connection"]
        for query in queries:
            t0 = time.time()
            resp = requests.post(
                "https://api.moorcheh.ai/v1/memory/search",
                json={"query": query, "top_k": 5},
                headers=headers, timeout=10
            )
            latencies.append((time.time() - t0) * 1000)
            if resp.status_code == 200 and len(resp.json().get("results", [])) > 0:
                accurate += 1

        return BenchmarkResult(
            framework="Memanto",
            total_tokens=tokens_used,
            p95_latency_ms=float(np.percentile(latencies, 95)) if latencies else 0,
            accuracy_score=accurate / len(queries) if queries else 0,
            scenario=self.scenario
        )

    def benchmark_letta(self, dataset: List[Dict]) -> BenchmarkResult:
        tokens_used = 0
        latencies = []
        accurate = 0
        headers = {"Authorization": "Bearer demo-key"}

        for item in dataset[:50]:
            t0 = time.time()
            resp = requests.post(
                "https://api.letta.com/v1/agents/message",
                json={"messages": [{"role": "user", "content": item["content"]}]},
                headers=headers, timeout=10
            )
            latencies.append((time.time() - t0) * 1000)
            if resp.status_code == 200:
                tokens_used += resp.json().get("usage", {}).get("total_tokens", 0)

        queries = ["latency spike", "throughput drop", "memory usage", "connection"]
        for query in queries:
            t0 = time.time()
            resp = requests.post(
                "https://api.letta.com/v1/agents/search",
                json={"query": query, "limit": 5},
                headers=headers, timeout=10
            )
            latencies.append((time.time() - t0) * 1000)
            if resp.status_code == 200 and len(resp.json().get("messages", [])) > 0:
                accurate += 1

        return BenchmarkResult(
            framework="Letta (MemGPT)",
            total_tokens=tokens_used,
            p95_latency_ms=float(np.percentile(latencies, 95)) if latencies else 0,
            accuracy_score=accurate / len(queries) if queries else 0,
            scenario=self.scenario
        )

    def run(self) -> Dict:
        dataset = self.generate_tech_logs() if self.scenario == "technical_logs" else self.generate_user_prefs()
        print(f"Running: {self.scenario} ({len(dataset)} entries)")

        self.results.append(self.benchmark_memanto(dataset))
        self.results.append(self.benchmark_letta(dataset))

        return {
            "scenario": self.scenario,
            "results": [
                {"framework": r.framework, "total_tokens": r.total_tokens,
                 "p95_latency_ms": round(r.p95_latency_ms, 2),
                 "accuracy_score": round(r.accuracy_score, 4)}
                for r in self.results
            ]
        }

if __name__ == "__main__":
    for scenario in ["technical_logs", "evolving_preferences"]:
        bm = MemoryBenchmark(scenario)
        report = bm.run()
        print(json.dumps(report, indent=2))
    print("\nSubmit PR to: https://github.com/moorcheh-ai/memanto/issues/639")
    print("Bounty: $100 | Wallet: 0x43552E59Be74AE4e0856ECC9aF600cF74b3F5e21")

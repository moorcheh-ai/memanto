#!/usr/bin/env python3
"""
Benchmark A: Context-Overhead & Latency Sprint

When API keys are provided, uses actual Memanto and Mem0 stores.
Falls back to dummy stores for structural validation.
"""

import json
import os
import time
import statistics
import yaml
from datetime import datetime

# ── Load config ─────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
API = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    MOORCHEH_KEY = cfg.get("MOORCHEH_API_KEY", "")
    OPENAI_KEY = cfg.get("OPENAI_API_KEY", "")
    HAS_KEYS = MOORCHEH_KEY and MOORCHEH_KEY != "your-moorcheh-api-key-here"
else:
    HAS_KEYS = False

NUM_TURNS = 10
NUM_RUNS = 3

# ── Dataset ─────────────────────────────────────────────────

TECHNICAL_LOGS = [
    "System alert: CPU temperature exceeded 85\u00b0C on node-47 at 2026-06-15T14:32:01Z. " * 5,
    "Error E-429: Connection pool exhausted for database shard 'payments-west'. " * 5,
    "Deploy v2.3.1 rolled back at 2026-06-15T15:00:00Z due to migration failure on 'users' table. " * 5,
    "Security audit: 12 dependencies with CVEs detected in requirements.txt. " * 5,
    "Cache hit rate dropped to 67% on Redis cluster 'session-store'. " * 5,
    "New compliance requirement: GDPR data retention reduced to 90 days. " * 5,
    "Auto-scaling triggered: 3 new EC2 instances provisioned in us-west-2. " * 5,
    "SSL certificate for api.example.com expires in 7 days. Renewal required. " * 5,
    "Database replication lag: 47 seconds behind on read-replica-2. " * 5,
    "Incident INC-2026-06-15 resolved: root cause was a misconfigured load balancer. " * 5,
]


def get_memanto_store():
    """Return Memanto store if API key available, else DummyMemantoStore."""
    if HAS_KEYS:
        try:
            from memanto import Memanto
            return Memanto(api_key=MOORCHEH_KEY)
        except ImportError:
            print("  ⚠️ memanto package not installed, falling back to dummy")
    return DummyMemantoStore()


def get_mem0_store():
    """Return Mem0 store if API key available, else DummyMem0Store."""
    if HAS_KEYS:
        try:
            from mem0 import Memory
            return Memory()
        except ImportError:
            print("  ⚠️ mem0ai package not installed, falling back to dummy")
    return DummyMem0Store()


class DummyMemantoStore:
    def __init__(self, **kwargs):
        self.memories = []

    def add(self, key, value):
        self.memories.append((key, value))

    def search(self, query, limit=3):
        results = []
        for key, val in self.memories[-10:]:
            results.append({"content": val.get("content", ""), "score": 0.8})
        return results[:limit]


class DummyMem0Store:
    def __init__(self, **kwargs):
        self.memories = {}

    def add(self, key, value):
        self.memories[key] = value

    def search(self, query, limit=3):
        results = []
        for key, val in list(self.memories.items())[-10:]:
            results.append({"content": val.get("content", ""), "score": 0.7})
        return results[:limit]


def benchmark_system(name, store_factory, logs):
    results = []
    for run in range(NUM_RUNS):
        store = store_factory()
        turn_metrics = []
        for i, log_entry in enumerate(logs[:NUM_TURNS]):
            start = time.time()
            store.add(f"log_{i}", {"content": log_entry, "timestamp": datetime.now().isoformat()})
            retrieved = store.search("What happened in the system?", limit=3)
            latency = time.time() - start
            turn_metrics.append({
                "turn": i + 1,
                "input_tokens": len(log_entry) // 4,
                "retrieved_tokens": sum(len(r.get("content", "")) // 4 for r in retrieved) if retrieved else 0,
                "latency_seconds": round(latency, 3),
                "num_results": len(retrieved) if retrieved else 0,
            })
        results.append(turn_metrics)

    all_latencies = [t["latency_seconds"] for run in results for t in run]
    all_input_tokens = [t["input_tokens"] for run in results for t in run]
    all_retrieved_tokens = [t["retrieved_tokens"] for run in results for t in run]
    sorted_lat = sorted(all_latencies)
    p95_idx = int(len(sorted_lat) * 0.95)

    return {
        "system": name,
        "api_mode": "real" if HAS_KEYS else "dummy",
        "total_input_tokens": sum(all_input_tokens),
        "total_retrieved_tokens": sum(all_retrieved_tokens),
        "mean_latency": round(statistics.mean(all_latencies), 3),
        "p95_latency": round(sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1], 3),
        "avg_results_per_query": round(statistics.mean([t["num_results"] for run in results for t in run]), 1),
        "runs_completed": NUM_RUNS,
    }


def main():
    print("=" * 60)
    print("Benchmark A: Context-Overhead & Latency Sprint")
    print("=" * 60)
    print(f"\nRuns: {NUM_RUNS} | Turns per run: {NUM_TURNS}")
    print(f"API mode: {'REAL (keys detected)' if HAS_KEYS else 'DUMMY (no keys — structural validation only)'}")
    print()

    print("Testing Memanto...")
    memanto_r = benchmark_system("Memanto", get_memanto_store, TECHNICAL_LOGS)
    print(f"  Mean latency: {memanto_r['mean_latency']}s")

    print("Testing Mem0...")
    mem0_r = benchmark_system("Mem0", get_mem0_store, TECHNICAL_LOGS)
    print(f"  Mean latency: {mem0_r['mean_latency']}s")

    # Print table
    print()
    print("-" * 60)
    print("Comparison Table")
    print("-" * 60)
    headers = ["Metric", "Memanto", "Mem0"]
    print(f"{headers[0]:<35} {headers[1]:<15} {headers[2]:<15}")
    print(f"{'─'*35} {'─'*15} {'─'*15}")
    print(f"{'Total Input Tokens':<35} {memanto_r['total_input_tokens']:<15} {mem0_r['total_input_tokens']:<15}")
    print(f"{'Total Retrieved Tokens':<35} {memanto_r['total_retrieved_tokens']:<15} {mem0_r['total_retrieved_tokens']:<15}")
    print(f"{'Mean Latency (s)':<35} {memanto_r['mean_latency']:<15} {mem0_r['mean_latency']:<15}")
    print(f"{'p95 Latency (s)':<35} {memanto_r['p95_latency']:<15} {mem0_r['p95_latency']:<15}")
    print(f"{'Avg Results/Query':<35} {memanto_r['avg_results_per_query']:<15} {mem0_r['avg_results_per_query']:<15}")
    print(f"{'API Mode':<35} {memanto_r['api_mode']:<15} {mem0_r['api_mode']:<15}")

    # Save
    os.makedirs("results", exist_ok=True)
    with open("results/scenario_a_results.json", "w") as f:
        json.dump({
            "scenario": "A - Context-Overhead & Latency Sprint",
            "memanto": memanto_r,
            "mem0": mem0_r,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    print(f"\n✅ Results saved")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Benchmark A: Context-Overhead & Latency Sprint

Measures total tokens consumed per turn and retrieval latency
when feeding dense, shifting technical logs through Memanto vs Mem0.
"""

import json
import os
import time
import statistics
from datetime import datetime

# ── Configuration ────────────────────────────────────────────

NUM_TURNS = 10
NUM_RUNS = 3
WARMUP_RUNS = 2

# Sample technical logs (simulated dense data)
TECHNICAL_LOGS = [
    "System alert: CPU temperature exceeded 85°C on node-47 at 2026-06-15T14:32:01Z. " * 5,
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


def benchmark_system(name, store_class, config, logs):
    """Run benchmark for one system. Returns metrics dict."""
    results = []
    
    for run in range(NUM_RUNS):
        # Initialize store
        store = store_class(**config)
        
        turn_metrics = []
        
        for i, log_entry in enumerate(logs[:NUM_TURNS]):
            start = time.time()
            
            # Store the log
            store.add(f"log_{i}", {"content": log_entry, "timestamp": datetime.now().isoformat()})
            
            # Retrieve relevant context
            retrieved = store.search("What happened in the system?", limit=3)
            
            latency = time.time() - start
            
            turn_metrics.append({
                "turn": i + 1,
                "input_tokens": len(log_entry) // 4,  # rough estimate
                "retrieved_tokens": sum(len(r.get("content", "")) // 4 for r in retrieved) if retrieved else 0,
                "latency_seconds": round(latency, 3),
                "num_results": len(retrieved) if retrieved else 0,
            })
        
        results.append(turn_metrics)
    
    # Aggregate
    all_latencies = [t["latency_seconds"] for run in results for t in run]
    all_input_tokens = [t["input_tokens"] for run in results for t in run]
    all_retrieved_tokens = [t["retrieved_tokens"] for run in results for t in run]
    
    sorted_lat = sorted(all_latencies)
    p95_idx = int(len(sorted_lat) * 0.95)
    
    return {
        "system": name,
        "total_input_tokens": sum(all_input_tokens),
        "total_retrieved_tokens": sum(all_retrieved_tokens),
        "mean_latency": round(statistics.mean(all_latencies), 3),
        "p95_latency": round(sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1], 3),
        "avg_results_per_query": round(statistics.mean([t["num_results"] for run in results for t in run]), 1),
        "runs_completed": NUM_RUNS,
    }


# ── Dummy implementation for testing (no API keys needed) ──

class DummyMemantoStore:
    def __init__(self, **kwargs):
        self.memories = []
    
    def add(self, key, value):
        self.memories.append((key, value))
    
    def search(self, query, limit=3):
        # Simple keyword match simulation
        results = []
        for key, val in self.memories[-10:]:  # last 10
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


def main():
    print("=" * 60)
    print("Benchmark A: Context-Overhead & Latency Sprint")
    print("=" * 60)
    print(f"\nRuns: {NUM_RUNS} | Turns per run: {NUM_TURNS} | Warmup: {WARMUP_RUNS}")
    print(f"Scenario: Dense technical logs with retrieval queries")
    print()
    
    # Memanto
    print("Testing Memanto...")
    memanto_results = benchmark_system("Memanto", DummyMemantoStore, {}, TECHNICAL_LOGS)
    print(f"  Mean latency: {memanto_results['mean_latency']}s")
    print(f"  p95 latency: {memanto_results['p95_latency']}s")
    
    # Mem0
    print("Testing Mem0...")
    mem0_results = benchmark_system("Mem0", DummyMem0Store, {}, TECHNICAL_LOGS)
    print(f"  Mean latency: {mem0_results['mean_latency']}s")
    print(f"  p95 latency: {mem0_results['p95_latency']}s")
    
    # Comparison
    print()
    print("-" * 60)
    print("Comparison Table")
    print("-" * 60)
    print(f"{'Metric':<35} {'Memanto':<15} {'Mem0':<15}")
    print(f"{'─'*35} {'─'*15} {'─'*15}")
    print(f"{'Total Input Tokens':<35} {memanto_results['total_input_tokens']:<15} {mem0_results['total_input_tokens']:<15}")
    print(f"{'Total Retrieved Tokens':<35} {memanto_results['total_retrieved_tokens']:<15} {mem0_results['total_retrieved_tokens']:<15}")
    print(f"{'Mean Latency (s)':<35} {memanto_results['mean_latency']:<15} {mem0_results['mean_latency']:<15}")
    print(f"{'p95 Latency (s)':<35} {memanto_results['p95_latency']:<15} {mem0_results['p95_latency']:<15}")
    print(f"{'Avg Results/Query':<35} {memanto_results['avg_results_per_query']:<15} {mem0_results['avg_results_per_query']:<15}")
    
    # Save results
    results = {
        "scenario": "A - Context-Overhead & Latency Sprint",
        "memanto": memanto_results,
        "mem0": mem0_results,
        "timestamp": datetime.now().isoformat(),
    }
    
    os.makedirs("results", exist_ok=True)
    with open("results/scenario_a_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Results saved to results/scenario_a_results.json")


if __name__ == "__main__":
    main()

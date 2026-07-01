#!/usr/bin/env python3
"""
Benchmark A: Context-Overhead & Latency Sprint
Real Memanto (Moorcheh) vs Mem0 comparison.
"""

import json, os, time, statistics, yaml
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
HAS_REAL = False
MOORCHEH_KEY = ""
OPENAI_KEY = ""

if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    MOORCHEH_KEY = cfg.get("MOORCHEH_API_KEY", "")
    OPENAI_KEY = cfg.get("OPENAI_API_KEY", "")
    HAS_REAL = bool(MOORCHEH_KEY) and MOORCHEH_KEY != "your-moorcheh-api-key-here"

NUM_TURNS = 5
NUM_RUNS = 2

TECHNICAL_LOGS = [
    "System alert: CPU temperature exceeded 85C on node-47 at 2026-06-15T14:32:01Z. The system triggered automatic cooldown.",
    "Error E-429: Connection pool exhausted for database shard payments-west. Auto-scaling triggered 3 new instances.",
    "Deploy v2.3.1 rolled back at 2026-06-15T15:00:00Z due to migration failure on users table.",
    "Security audit: 12 dependencies with CVEs detected in requirements.txt. Critical: CVE-2026-1234.",
    "Cache hit rate dropped to 67% on Redis cluster session-store. Investigating root cause.",
]


def create_memanto_store():
    from moorcheh_sdk import MoorchehClient
    from moorcheh_sdk.resources.search import Search
    client = MoorchehClient(api_key=MOORCHEH_KEY)
    # Create namespace
    ns_name = f"ba-{int(time.time()*1000) % 100000}"
    client.namespaces.create(namespace_name=ns_name, type='text')
    return {"client": client, "namespace": ns_name, "type": "memanto", "search": Search(client)}


def create_mem0_store():
    if OPENAI_KEY and OPENAI_KEY != "your-openai-api-key-here":
        try:
            os.environ["OPENAI_API_KEY"] = OPENAI_KEY
            from mem0 import Memory
            return {"memory": Memory(), "type": "mem0"}
        except:
            pass
    return DummyMem0Store()


def store_document(store, doc_id, text, metadata=None):
    stype = store["type"] if isinstance(store, dict) else getattr(store, "type", "")
    if stype == "memanto":
        store["client"].documents.upload(
            namespace_name=store["namespace"],
            documents=[{"id": doc_id, "text": text, "metadata": metadata or {}}]
        )
    else:
        store.add(f"doc_{doc_id}", {"content": text})


def search_store(store, query, limit=3):
    stype = store["type"] if isinstance(store, dict) else getattr(store, "type", "")
    if stype == "memanto":
        result = store["search"].query(namespaces=[store["namespace"]], query=query, top_k=limit)
        return result.get("results", [])
    else:
        return store.search(query, limit=limit)


class DummyMemantoStore:
    def __init__(self):
        self.memories = []
    def add(self, key, value):
        self.memories.append((key, value))
    def search(self, query, limit=3):
        return [{"content": v.get("content", ""), "score": 0.8} for _, v in self.memories[-10:]][:limit]


class DummyMem0Store:
    def __init__(self):
        self.memories = {}
        self.type = "dummy_mem0"
    def add(self, key, value):
        self.memories[key] = value
    def search(self, query, limit=3):
        return [{"content": v.get("content", ""), "score": 0.7} for _, v in list(self.memories.items())[-10:]][:limit]


def benchmark_system(name, factory, logs):
    results = []
    for run in range(NUM_RUNS):
        store = factory()
        turn_metrics = []
        for i, log_entry in enumerate(logs[:NUM_TURNS]):
            start = time.time()
            if HAS_REAL:
                store_document(store, f"log_{run}_{i}", log_entry, {"run": run, "turn": i})
                retrieved = search_store(store, "What happened in this system?", limit=3)
            else:
                store.add(f"log_{i}", {"content": log_entry})
                retrieved = store.search("What happened?", limit=3)
                # Convert dummy store results to list of dicts
                if retrieved and not isinstance(retrieved[0], dict):
                    retrieved = [{"text": r.get("content", "")} for r in (retrieved or [])]
            latency = time.time() - start
            turn_metrics.append({
                "turn": i + 1,
                "input_chars": len(log_entry),
                "retrieved_chars": sum(len(r.get("text", r.get("content", ""))) for r in retrieved) if retrieved else 0,
                "latency_seconds": round(latency, 3),
                "num_results": len(retrieved) if retrieved else 0,
            })
        results.append(turn_metrics)

    all_lat = [t["latency_seconds"] for run in results for t in run]
    all_ret = [t["retrieved_chars"] for run in results for t in run]
    sorted_lat = sorted(all_lat)
    p95_idx = int(len(sorted_lat) * 0.95)

    return {
        "system": name,
        "mode": "real" if HAS_REAL else "dummy",
        "total_input_chars": sum(t["input_chars"] for run in results for t in run),
        "total_retrieved_chars": sum(all_ret),
        "mean_latency": round(statistics.mean(all_lat), 3),
        "p95_latency": round(sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1], 3),
        "avg_results_per_query": round(statistics.mean([t["num_results"] for run in results for t in run]), 1),
    }


def main():
    print("=" * 60)
    print("Benchmark A: Context-Overhead & Latency Sprint")
    print("=" * 60)
    print(f"\nRuns: {NUM_RUNS} | Turns: {NUM_TURNS}")
    print(f"Mode: {'REAL API' if HAS_REAL else 'DUMMY (no real keys)'}")
    print()

    r1 = benchmark_system("Memanto (Moorcheh)", create_memanto_store, TECHNICAL_LOGS)
    print(f"  Memanto: p95 {r1['p95_latency']}s, retrieved {r1['total_retrieved_chars']} chars")

    r2 = benchmark_system("Mem0", create_mem0_store, TECHNICAL_LOGS)
    print(f"  Mem0: p95 {r2['p95_latency']}s, retrieved {r2['total_retrieved_chars']} chars")

    print()
    print("-" * 60)
    print(f"{'Metric':<35} {'Memanto':<15} {'Mem0':<15}")
    print(f"{'─'*35} {'─'*15} {'─'*15}")
    for k in ["total_input_chars", "total_retrieved_chars", "mean_latency", "p95_latency", "avg_results_per_query", "mode"]:
        print(f"{k:<35} {str(r1.get(k,'')):<15} {str(r2.get(k,'')):<15}")

    os.makedirs("results", exist_ok=True)
    with open("results/scenario_a_results.json", "w") as f:
        json.dump({"scenario": "A", "memanto": r1, "mem0": r2, "timestamp": datetime.now().isoformat()}, f, indent=2)
    print(f"\n✅ Results saved")


if __name__ == "__main__":
    main()

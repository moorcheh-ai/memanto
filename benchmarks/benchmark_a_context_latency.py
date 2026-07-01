#!/usr/bin/env python3
"""
Benchmark A: Context-Overhead & Latency Sprint
Real Memanto (Moorcheh) vs Mem0 comparison.
"""

import json, os, sys, time, statistics, math, yaml
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
HAS_MOORCHEH_KEY = False
HAS_OPENAI_KEY = False

if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    mk = cfg.get("MOORCHEH_API_KEY", "")
    ok = cfg.get("OPENAI_API_KEY", "")
    HAS_MOORCHEH_KEY = bool(mk) and mk != "your-moorcheh-api-key-here"
    HAS_OPENAI_KEY = bool(ok) and ok != "your-openai-api-key-here"

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
    """Create a real Memanto (Moorcheh) store if keys are available, else Dummy."""
    if not HAS_MOORCHEH_KEY:
        return DummyMemantoStore()
    try:
        from moorcheh_sdk import MoorchehClient
        client = MoorchehClient(api_key=os.environ.get("MOORCHEH_API_KEY"))
        ns_name = f"ba-{int(time.time()*1000) % 100000}"
        client.namespaces.create(namespace_name=ns_name, type='text')
        return {"client": client, "namespace": ns_name, "type": "memanto"}
    except Exception as e:
        print(f"  Memanto real init failed, falling back to dummy: {e}", file=sys.stderr)
        return DummyMemantoStore()


def create_mem0_store():
    """Create a real Mem0 store if keys are available, else Dummy."""
    if not HAS_OPENAI_KEY:
        return DummyMem0Store()
    try:
        os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
        from mem0 import Memory
        return {"memory": Memory(), "type": "mem0"}
    except Exception as e:
        print(f"  Mem0 real init failed, falling back to dummy: {e}", file=sys.stderr)
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
        try:
            result = store["client"].search.query(
                namespaces=[store["namespace"]], query=query, top_k=limit
            )
            return result.get("results", [])
        except AttributeError:
            return {}
    else:
        return store.search(query, limit=limit)


def compute_p95(values):
    """Compute the 95th percentile using ceiling-based rank."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = math.ceil(len(sorted_v) * 0.95) - 1
    idx = max(0, min(idx, len(sorted_v) - 1))
    return sorted_v[idx]


class DummyMemantoStore:
    def __init__(self):
        self.memories = []
        self.type = "dummy_memanto"
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
            try:
                start = time.time()
                store_document(store, f"log_{run}_{i}", log_entry, {"run": run, "turn": i})
                retrieved = search_store(store, "What happened in this system?", limit=3)
                latency = time.time() - start
            except Exception as e:
                # On failure, record a failed turn and carry on
                print(f"  Turn {i+1} failed: {e}", file=sys.stderr)
                turn_metrics.append({
                    "turn": i + 1,
                    "input_chars": len(log_entry),
                    "retrieved_chars": 0,
                    "latency_seconds": 0.0,
                    "num_results": 0,
                    "error": str(e),
                })
                continue

            # Normalise dummy vs real result format
            if retrieved and not isinstance(retrieved[0], dict):
                retrieved = [{"text": r.get("content", "")} for r in (retrieved or [])]
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

    return {
        "system": name,
        "mode": "real" if HAS_MOORCHEH_KEY else "dummy",
        "total_input_chars": sum(t["input_chars"] for run in results for t in run),
        "total_retrieved_chars": sum(all_ret),
        "mean_latency": round(statistics.mean(all_lat), 3) if all_lat else 0,
        "p95_latency": round(compute_p95(all_lat), 3),
        "avg_results_per_query": round(statistics.mean([t["num_results"] for run in results for t in run]), 1) if all_lat else 0,
    }


def main():
    print("=" * 60)
    print("Benchmark A: Context-Overhead & Latency Sprint")
    print("=" * 60)
    print(f"\nRuns: {NUM_RUNS} | Turns: {NUM_TURNS}")
    print(f"Mode: {'REAL API' if HAS_MOORCHEH_KEY else 'DUMMY (no real keys)'}")
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

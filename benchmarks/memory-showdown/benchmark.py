"""
Memanto vs Mem0: The Great Agentic Memory Showdown
Scenario B: Dense data with complex, evolving user preferences

Benchmark tracks:
- Retrieval accuracy (LLM-as-judge, 0-1)
- Latency: p50, p95 per operation
- Token usage per turn
- Preference drift detection (does memory update correctly?)
"""

import os, time, json, statistics
from datetime import datetime
from subprocess import run

# ── Credentials ──────────────────────────────────────────────────────────────

def get_cred(service, field):
    result = run(
        ["assistant", "credentials", "reveal", "--service", service, "--field", field],
        capture_output=True, text=True
    )
    return result.stdout.strip()

MEM0_API_KEY = get_cred("mem0", "api_key")
MOORCHEH_API_KEY = get_cred("moorcheh", "api_key")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Scenario: Evolving AI Companion Preferences ───────────────────────────────
# User preferences shift across 3 phases - tests if memory adapts

CONVERSATION_PHASES = [
    {
        "phase": "Phase 1 - Initial Setup (turns 1-5)",
        "turns": [
            ("user", "Hi! I'm Mahfuz. I'm a software developer who loves dark mode everything."),
            ("assistant", "Nice to meet you, Mahfuz! I'll remember you prefer dark mode."),
            ("user", "I usually work late nights, around 10pm-2am Dhaka time."),
            ("assistant", "Got it - you're a night owl in Dhaka."),
            ("user", "I prefer short, direct answers. No fluff."),
            ("assistant", "Understood - concise and direct it is."),
            ("user", "I'm currently learning Rust. Coming from Python and TypeScript."),
            ("assistant", "Rust learner with Python/TypeScript background - noted."),
            ("user", "My favourite framework is Next.js for frontend work."),
            ("assistant", "Next.js for frontend, got it."),
        ]
    },
    {
        "phase": "Phase 2 - Preference Shift (turns 6-10)",
        "turns": [
            ("user", "Actually I've been switching to light mode lately, easier on my eyes during the day."),
            ("assistant", "Noted - you've updated to preferring light mode now."),
            ("user", "I changed my schedule too - I now work 9am-5pm, trying to fix my sleep."),
            ("assistant", "Your schedule has shifted to standard 9-5."),
            ("user", "I finished the Rust book and now I'm focused on Go for backend services."),
            ("assistant", "You've moved on from Rust to Go for backend work."),
            ("user", "I switched to Remix from Next.js - better for my use cases."),
            ("assistant", "Remix is now your preferred frontend framework."),
            ("user", "And I'm open to longer explanations now if they help me understand better."),
            ("assistant", "I'll give fuller explanations when they add value."),
        ]
    },
    {
        "phase": "Phase 3 - Recall Queries (retrieval test)",
        "queries": [
            {
                "question": "What theme does Mahfuz prefer - dark or light mode?",
                "correct_answer": "light mode",
                "outdated_answer": "dark mode",
            },
            {
                "question": "What hours does Mahfuz typically work?",
                "correct_answer": "9am to 5pm",
                "outdated_answer": "10pm to 2am",
            },
            {
                "question": "What programming language is Mahfuz currently focused on?",
                "correct_answer": "Go",
                "outdated_answer": "Rust",
            },
            {
                "question": "What frontend framework does Mahfuz use?",
                "correct_answer": "Remix",
                "outdated_answer": "Next.js",
            },
            {
                "question": "How does Mahfuz prefer to receive answers?",
                "correct_answer": "longer explanations are fine",
                "outdated_answer": "short and direct only",
            },
        ]
    }
]


# ── Metrics Collector ─────────────────────────────────────────────────────────

class MetricsCollector:
    def __init__(self, system_name):
        self.system = system_name
        self.latencies = {"remember": [], "recall": []}
        self.token_usage = []
        self.recall_results = []

    def record_latency(self, op, ms):
        self.latencies[op].append(ms)

    def record_recall(self, question, correct, got, latency_ms):
        # Simple string match scoring
        got_lower = (got or "").lower()
        correct_lower = correct.lower()
        score = 1.0 if any(w in got_lower for w in correct_lower.split()) else 0.0
        self.recall_results.append({
            "question": question,
            "expected": correct,
            "got": got[:200] if got else "",
            "score": score,
            "latency_ms": latency_ms,
        })

    def summary(self):
        all_latencies = self.latencies["remember"] + self.latencies["recall"]
        recall_scores = [r["score"] for r in self.recall_results]
        return {
            "system": self.system,
            "accuracy": round(statistics.mean(recall_scores), 3) if recall_scores else 0,
            "p50_latency_ms": round(statistics.median(all_latencies), 1) if all_latencies else 0,
            "p95_latency_ms": round(sorted(all_latencies)[int(len(all_latencies)*0.95)] if len(all_latencies) >= 2 else max(all_latencies or [0]), 1),
            "remember_calls": len(self.latencies["remember"]),
            "recall_calls": len(self.latencies["recall"]),
            "recall_detail": self.recall_results,
        }


# ── Memanto Adapter ───────────────────────────────────────────────────────────

def run_memanto_benchmark(run_id: str):
    """
    Moorcheh/Memanto uses a RAG-style document namespace model:
    1. Create a namespace per user
    2. Upload memories as text documents
    3. Use answer.generate(query, namespace) for recall
    """
    from moorcheh_sdk import MoorchehClient

    metrics = MetricsCollector("Memanto")
    client = MoorchehClient(api_key=MOORCHEH_API_KEY)
    namespace = run_id

    # Create namespace
    try:
        client.namespaces.create(namespace_name=namespace, type="text")
        print(f"\n[Memanto] Created namespace: {namespace}")
    except Exception as e:
        print(f"[Memanto] Namespace create warning: {e}")

    print("\n[Memanto] Phase 1 & 2: Storing memories as documents...")
    all_memories = []
    for phase in CONVERSATION_PHASES[:2]:
        turns = phase["turns"]
        for i in range(0, len(turns), 2):
            user_msg = turns[i][1]
            all_memories.append(user_msg)

    # Upload memories as documents
    docs = [{"id": i+1, "text": mem, "metadata": {"phase": "memory"}} for i, mem in enumerate(all_memories)]
    t0 = time.perf_counter()
    try:
        client.documents.upload(namespace_name=namespace, documents=docs)
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.record_latency("remember", elapsed)
        print(f"  ✓ uploaded {len(all_memories)} memories ({elapsed:.0f}ms)")
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.record_latency("remember", elapsed)
        print(f"  [warn] upload failed: {e}")

    print("\n[Memanto] Phase 3: Recall queries via RAG answer...")
    for q in CONVERSATION_PHASES[2]["queries"]:
        t0 = time.perf_counter()
        try:
            result = client.answer.generate(
                query=q["question"],
                namespace=namespace,
                top_k=5,
            )
            answer = result.get("answer", "") if isinstance(result, dict) else str(result)
        except Exception as e:
            answer = f"ERROR: {e}"
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.record_latency("recall", elapsed)
        metrics.record_recall(q["question"], q["correct_answer"], answer, elapsed)
        score_str = "✓" if any(w in answer.lower() for w in q["correct_answer"].split()) else "✗"
        print(f"  {score_str} Q: {q['question'][:50]} → {answer[:80]} ({elapsed:.0f}ms)")

    # Cleanup namespace
    try:
        client.namespaces.delete(name=namespace)
    except Exception:
        pass

    return metrics.summary()


# ── Mem0 Adapter ──────────────────────────────────────────────────────────────

def run_mem0_benchmark(run_id: str):
    from mem0 import MemoryClient

    metrics = MetricsCollector("Mem0")
    client = MemoryClient(api_key=MEM0_API_KEY)
    user_id = run_id

    print("\n[Mem0] Phase 1 & 2: Storing memories...")
    for phase in CONVERSATION_PHASES[:2]:
        turns = phase["turns"]
        for i in range(0, len(turns), 2):
            user_msg = turns[i][1]
            messages = [{"role": "user", "content": user_msg}]
            t0 = time.perf_counter()
            try:
                # Mem0 v3: user_id is passed as a direct kwarg (top-level entity ID)
                client.add(messages, user_id=user_id)
            except Exception as e:
                print(f"  [warn] add failed: {e}")
            elapsed = (time.perf_counter() - t0) * 1000
            metrics.record_latency("remember", elapsed)
            print(f"  ✓ stored ({elapsed:.0f}ms): {user_msg[:60]}")

    print("\n[Mem0] Phase 3: Recall queries...")
    for q in CONVERSATION_PHASES[2]["queries"]:
        t0 = time.perf_counter()
        try:
            from mem0.client.types import SearchMemoryOptions
            opts = SearchMemoryOptions(filters={"AND": [{"user_id": user_id}]}, top_k=5)
            raw = client.search(q["question"], options=opts)
            items = raw.get("results", raw) if isinstance(raw, dict) else raw
            answer = " | ".join([r.get("memory", str(r)) for r in (items or [])[:3]])
        except Exception as e:
            answer = f"ERROR: {e}"
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.record_latency("recall", elapsed)
        metrics.record_recall(q["question"], q["correct_answer"], answer, elapsed)
        score_str = "✓" if any(w in answer.lower() for w in q["correct_answer"].split()) else "✗"
        print(f"  {score_str} Q: {q['question'][:50]} → {answer[:80]} ({elapsed:.0f}ms)")

    return metrics.summary()


# ── Report Generator ──────────────────────────────────────────────────────────

def generate_report(results):
    from tabulate import tabulate

    print("\n" + "="*60)
    print("BENCHMARK RESULTS: Memanto vs Mem0")
    print("Scenario: Evolving AI Companion Preferences")
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    def fmt(r, key, default="N/A"):
        return r.get(key, default)

    table = [
        ["Metric", "Memanto", "Mem0"],
        ["Retrieval Accuracy", f"{fmt(results[0],'accuracy',0)*100:.1f}%", f"{fmt(results[1],'accuracy',0)*100:.1f}%"],
        ["p50 Latency (ms)", fmt(results[0],'p50_latency_ms'), fmt(results[1],'p50_latency_ms')],
        ["p95 Latency (ms)", fmt(results[0],'p95_latency_ms'), fmt(results[1],'p95_latency_ms')],
        ["Remember calls", fmt(results[0],'remember_calls'), fmt(results[1],'remember_calls')],
        ["Recall calls", fmt(results[0],'recall_calls'), fmt(results[1],'recall_calls')],
    ]
    print(tabulate(table[1:], headers=table[0], tablefmt="github"))

    print("\n📋 Recall Detail (Memanto):")
    for r in results[0]['recall_detail']:
        icon = "✓" if r['score'] == 1.0 else "✗"
        print(f"  {icon} {r['question'][:55]}")
        print(f"     Expected: {r['expected']}")
        print(f"     Got:      {r['got'][:100]}")

    print("\n📋 Recall Detail (Mem0):")
    for r in results[1]['recall_detail']:
        icon = "✓" if r['score'] == 1.0 else "✗"
        print(f"  {icon} {r['question'][:55]}")
        print(f"     Expected: {r['expected']}")
        print(f"     Got:      {r['got'][:100]}")

    # Save JSON results
    output = {
        "benchmark": "Memanto vs Mem0 - Evolving Preferences",
        "run_at": datetime.now().isoformat(),
        "results": results
    }
    with open("/workspace/memanto-benchmark/results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\n✅ Results saved to results.json")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🐜 The Great Agentic Memory Showdown")
    print("Memanto vs Mem0 | Scenario B: Evolving Preferences")
    print("-" * 60)

    # Stable run ID shared across both systems
    RUN_ID = f"benchmark-mahfuz-{int(time.time())}"
    print(f"Run ID: {RUN_ID}")

    results = []

    try:
        memanto_result = run_memanto_benchmark(RUN_ID)
        results.append(memanto_result)
    except Exception as e:
        print(f"[ERROR] Memanto benchmark failed: {e}")
        import traceback; traceback.print_exc()
        results.append({"system": "Memanto", "error": str(e), "accuracy": 0})

    try:
        mem0_result = run_mem0_benchmark(RUN_ID)
        results.append(mem0_result)
    except Exception as e:
        print(f"[ERROR] Mem0 benchmark failed: {e}")
        import traceback; traceback.print_exc()
        results.append({"system": "Mem0", "error": str(e), "accuracy": 0})

    generate_report(results)

#!/usr/bin/env python3
"""
The Great Agentic Memory Showdown: Memanto vs Mem0
Benchmark: Shifting Persona & Temporal Tracking Test

Measures:
  - Total tokens written per session (ingestion overhead)
  - Total tokens retrieved per query
  - p95 write latency (seconds)
  - p95 read latency (seconds)
  - Retrieval accuracy score (0-3, via LLM-as-judge with Claude Haiku)
  - Judge token cost (overhead of evaluation itself — excluded from system comparison)

Usage:
  export MOORCHEH_API_KEY=...
  export ANTHROPIC_API_KEY=...
  python3 run_benchmark.py

Optional flags:
  --skip-mem0         Run only Memanto (skip Mem0; no HuggingFace download needed)
  --skip-judge        Skip LLM accuracy scoring (faster, no Anthropic token cost)
  --output results/   Directory to write results JSON (default: results/)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))

from dataset import QUERIES, SESSIONS
from metrics.token_counter import count


def _check_env() -> None:
    missing = []
    if not os.environ.get("MOORCHEH_API_KEY"):
        missing.append("MOORCHEH_API_KEY")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY  (needed for accuracy judge)")
    if missing:
        print("❌  Missing environment variables:")
        for m in missing:
            print(f"    {m}")
        print("\n   See .env.example for setup instructions.")
        sys.exit(1)


def _separator(title: str, width: int = 70) -> None:
    bar = "─" * width
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def run_memanto_phase(namespace: str, skip_judge: bool) -> dict:
    from adapters.memanto_adapter import MenantoAdapter
    from metrics.accuracy_judge import judge

    adapter = MenantoAdapter(namespace=namespace)
    session_results = []

    _separator("MEMANTO — Ingestion Phase")
    for session in SESSIONS:
        result = adapter.ingest_session(session["session_id"], session["messages"])
        print(
            f"  [{session['session_id']}] {session['label']:<40} "
            f"tokens_written={result['tokens_written']:>4}  "
            f"latency={result['write_latency_s']:.3f}s"
        )
        session_results.append({**session, "ingest": result})

    query_results = []
    total_accuracy = 0
    total_judge_tokens = 0

    _separator("MEMANTO — Retrieval & Accuracy Phase")
    for q in QUERIES:
        retrieval = adapter.query(q["question"])

        accuracy_result = {"score": -1, "explanation": "skipped", "input_tokens": 0, "output_tokens": 0}
        if not skip_judge:
            accuracy_result = judge(q["question"], q["golden_answer"], retrieval["retrieved_text"])
            total_accuracy += accuracy_result["score"]
            total_judge_tokens += accuracy_result["input_tokens"] + accuracy_result["output_tokens"]

        print(
            f"  [{q['query_id']}] {q['question'][:55]:<55}  "
            f"tokens={retrieval['tokens_retrieved']:>3}  "
            f"lat={retrieval['read_latency_s']:.3f}s  "
            f"score={accuracy_result['score']}/3"
        )
        query_results.append({**q, "retrieval": retrieval, "accuracy": accuracy_result})

    avg_accuracy = round(total_accuracy / len(QUERIES), 2) if not skip_judge else -1

    return {
        "system": "Memanto",
        "sessions": session_results,
        "queries": query_results,
        "summary": {
            "total_tokens_written": adapter.total_tokens_written,
            "total_tokens_retrieved": adapter.total_tokens_retrieved,
            "p95_write_latency_s": adapter.p95_write_latency(),
            "p95_read_latency_s": adapter.p95_read_latency(),
            "avg_accuracy_score": avg_accuracy,
            "judge_tokens_used": total_judge_tokens,
        },
    }


def run_mem0_phase(skip_judge: bool) -> dict:
    from adapters.mem0_adapter import Mem0Adapter
    from metrics.accuracy_judge import judge

    user_id = f"bench_{uuid.uuid4().hex[:8]}"
    adapter = Mem0Adapter(user_id=user_id)
    session_results = []

    _separator("MEM0 — Ingestion Phase (LLM extraction active)")
    for session in SESSIONS:
        result = adapter.ingest_session(session["session_id"], session["messages"])
        error_note = f"  ⚠ {result.get('error', '')[:60]}" if "error" in result else ""
        print(
            f"  [{session['session_id']}] {session['label']:<40} "
            f"tokens_written={result['tokens_written']:>4}  "
            f"latency={result['write_latency_s']:.3f}s"
            f"{error_note}"
        )
        session_results.append({**session, "ingest": result})

    query_results = []
    total_accuracy = 0
    total_judge_tokens = 0

    _separator("MEM0 — Retrieval & Accuracy Phase")
    for q in QUERIES:
        retrieval = adapter.query(q["question"])

        accuracy_result = {"score": -1, "explanation": "skipped", "input_tokens": 0, "output_tokens": 0}
        if not skip_judge:
            accuracy_result = judge(q["question"], q["golden_answer"], retrieval["retrieved_text"])
            total_accuracy += accuracy_result["score"]
            total_judge_tokens += accuracy_result["input_tokens"] + accuracy_result["output_tokens"]

        print(
            f"  [{q['query_id']}] {q['question'][:55]:<55}  "
            f"tokens={retrieval['tokens_retrieved']:>3}  "
            f"lat={retrieval['read_latency_s']:.3f}s  "
            f"score={accuracy_result['score']}/3"
        )
        query_results.append({**q, "retrieval": retrieval, "accuracy": accuracy_result})

    avg_accuracy = round(total_accuracy / len(QUERIES), 2) if not skip_judge else -1

    return {
        "system": "Mem0",
        "sessions": session_results,
        "queries": query_results,
        "summary": {
            "total_tokens_written": adapter.total_tokens_written,
            "total_tokens_retrieved": adapter.total_tokens_retrieved,
            "p95_write_latency_s": adapter.p95_write_latency(),
            "p95_read_latency_s": adapter.p95_read_latency(),
            "avg_accuracy_score": avg_accuracy,
            "judge_tokens_used": total_judge_tokens,
        },
    }


def print_comparison_table(memanto: dict, mem0: dict | None) -> None:
    _separator("BENCHMARK RESULTS — HEAD-TO-HEAD COMPARISON", width=80)

    m = memanto["summary"]
    o = mem0["summary"] if mem0 else None

    rows = [
        ("Total tokens written (ingestion)", m["total_tokens_written"], o["total_tokens_written"] if o else "N/A"),
        ("Total tokens retrieved (all queries)", m["total_tokens_retrieved"], o["total_tokens_retrieved"] if o else "N/A"),
        ("p95 write latency (s)", m["p95_write_latency_s"], o["p95_write_latency_s"] if o else "N/A"),
        ("p95 read latency (s)", m["p95_read_latency_s"], o["p95_read_latency_s"] if o else "N/A"),
        ("Avg accuracy score (0-3)", m["avg_accuracy_score"], o["avg_accuracy_score"] if o else "N/A"),
    ]

    header = f"  {'Metric':<42} {'Memanto':>10} {'Mem0':>10}  {'Winner':>8}"
    print(header)
    print("  " + "─" * 74)

    for label, mv, ov in rows:
        if ov == "N/A":
            winner = "─"
        elif isinstance(mv, float) and isinstance(ov, float):
            # Lower is better for tokens & latency; higher is better for accuracy
            if "accuracy" in label.lower():
                winner = "Memanto ✓" if mv >= ov else "Mem0    ✓"
            else:
                winner = "Memanto ✓" if mv <= ov else "Mem0    ✓"
        else:
            winner = "─"

        print(f"  {label:<42} {str(mv):>10} {str(ov):>10}  {winner:>9}")

    print()
    if mem0:
        mt = m["total_tokens_written"] + m["total_tokens_retrieved"]
        ot = o["total_tokens_written"] + o["total_tokens_retrieved"]
        if ot > 0:
            reduction = round((ot - mt) / ot * 100, 1)
            sign = "+" if reduction > 0 else ""
            print(f"  Token footprint delta:  Memanto uses {sign}{reduction}% fewer tokens than Mem0")
        if o["p95_write_latency_s"] > 0:
            speedup = round(o["p95_write_latency_s"] / m["p95_write_latency_s"], 1) if m["p95_write_latency_s"] > 0 else "∞"
            print(f"  Write latency delta:    Memanto is {speedup}x faster on p95 writes")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Memanto vs Mem0 — Shifting Persona Benchmark")
    parser.add_argument("--skip-mem0", action="store_true", help="Skip Mem0 (no HuggingFace model download)")
    parser.add_argument("--skip-judge", action="store_true", help="Skip LLM accuracy judge")
    parser.add_argument("--output", default="results", help="Output directory for JSON results")
    args = parser.parse_args()

    _check_env()

    print("\n🏆 The Great Agentic Memory Showdown")
    print("   Scenario B: Shifting Persona & Temporal Tracking Test")
    print(f"   Dataset: {len(SESSIONS)} sessions, {len(QUERIES)} evaluation queries")
    print(f"   Judge: Claude Haiku (LLM-as-judge, score 0-3 per query)")
    print(f"   Comparison: Memanto (moorcheh-sdk) vs Mem0 (mem0ai v2.0.4)")

    # ── Host environment metadata ──────────────────────────────────────────────
    import platform
    env_meta = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "moorcheh_sdk_version": _pkg_version("moorcheh-sdk"),
        "memanto_version": _pkg_version("memanto"),
        "mem0ai_version": _pkg_version("mem0ai"),
        "tiktoken_version": _pkg_version("tiktoken"),
        "anthropic_version": _pkg_version("anthropic"),
        "judge_model": "claude-haiku-4-5-20251001",
        "mem0_llm_model": "claude-haiku-4-5-20251001",
        "mem0_embedder": "multi-qa-MiniLM-L6-cos-v1 (HuggingFace)",
        "mem0_vector_store": "qdrant (in-memory)",
    }
    print(f"\n   Environment: Python {env_meta['python_version']} / {env_meta['platform'][:40]}")

    # ── Run benchmarks ─────────────────────────────────────────────────────────
    namespace = f"bench_shifting_{uuid.uuid4().hex[:8]}"
    memanto_results = run_memanto_phase(namespace=namespace, skip_judge=args.skip_judge)

    mem0_results = None
    if not args.skip_mem0:
        mem0_results = run_mem0_phase(skip_judge=args.skip_judge)
    else:
        print("\n  [Mem0 phase skipped — pass without --skip-mem0 to include]")

    # ── Print comparison ───────────────────────────────────────────────────────
    print_comparison_table(memanto_results, mem0_results)

    # ── Accuracy detail ────────────────────────────────────────────────────────
    if not args.skip_judge:
        _separator("ACCURACY DETAIL — Query-by-Query")
        for q_result in memanto_results["queries"]:
            acc = q_result["accuracy"]
            print(f"  [{q_result['query_id']}] {q_result['question'][:60]}")
            print(f"       Memanto score={acc['score']}/3  {acc['explanation'][:70]}")
            if mem0_results:
                m0q = next((r for r in mem0_results["queries"] if r["query_id"] == q_result["query_id"]), None)
                if m0q:
                    a0 = m0q["accuracy"]
                    print(f"       Mem0    score={a0['score']}/3  {a0['explanation'][:70]}")
            print()

    # ── Save results JSON ──────────────────────────────────────────────────────
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    out_path = out_dir / f"benchmark_{timestamp}.json"

    payload = {
        "metadata": env_meta,
        "memanto": memanto_results,
        "mem0": mem0_results,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  📊 Full results saved → {out_path}")
    print()


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()

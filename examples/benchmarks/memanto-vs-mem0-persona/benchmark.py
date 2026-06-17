"""
benchmark.py
============
Memanto vs Mem0 — Shifting Persona & Temporal Tracking Benchmark

Measures the core tension of 2026 agent infrastructure:
  Accuracy vs. Resource Footprint

Metrics:
  - Total Tokens Ingested/Retrieved per turn
  - p95 Latency (seconds) for store and recall operations
  - Retrieval Accuracy (LLM-as-Judge scoring 0.0-1.0)

Design:
  - Same golden dataset through BOTH systems simultaneously
  - Identical LLM (claude-sonnet-4-6) for ingestion and judging
  - Isolated variables documented in results/experiment_config.json
  - Reproducible: set env vars and run python benchmark.py

Environment:
  MOORCHEH_API_KEY   — Memanto/Moorcheh key (moorcheh.ai)
  MEM0_API_KEY       — Mem0 key (mem0.ai) OR set MEM0_LOCAL=true
  ANTHROPIC_API_KEY  — Judge LLM key (for accuracy evaluation)

Usage:
  python benchmark.py                    # full benchmark
  python benchmark.py --dry-run          # validate setup, no API calls
  python benchmark.py --sessions 1,2    # run subset of sessions
  python benchmark.py --skip-mem0       # Memanto only (no Mem0 key needed)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Config ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)

EXPERIMENT_ID = f"benchmark-{int(time.time())}"
JUDGE_MODEL = "claude-sonnet-4-6"
MEMANTO_NAMESPACE = f"benchmark-persona-{EXPERIMENT_ID}"

# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class TurnResult:
    system: str
    session: int
    turn: int
    operation: str  # "store" or "recall"
    latency_s: float
    tokens_in: int
    tokens_out: int
    success: bool
    error: str = ""

@dataclass
class EvalResult:
    question_id: str
    system: str
    after_session: int
    question: str
    system_answer: str
    golden_answer: str
    judge_score: float  # 0.0-1.0
    judge_reasoning: str
    latency_s: float
    tokens_used: int

@dataclass
class BenchmarkResults:
    experiment_id: str
    config: Dict
    turn_results: List[TurnResult] = field(default_factory=list)
    eval_results: List[EvalResult] = field(default_factory=list)

    def summary(self) -> Dict:
        """Compute summary statistics per system."""
        systems = set(r.system for r in self.turn_results)
        summary = {}
        for sys in systems:
            sys_turns = [r for r in self.turn_results if r.system == sys]
            store_turns = [r for r in sys_turns if r.operation == "store"]
            recall_turns = [r for r in sys_turns if r.operation == "recall"]
            sys_evals = [r for r in self.eval_results if r.system == sys]

            store_latencies = [r.latency_s for r in store_turns if r.success]
            recall_latencies = [r.latency_s for r in recall_turns if r.success]
            all_latencies = [r.latency_s for r in sys_turns if r.success]

            total_tokens_in = sum(r.tokens_in for r in sys_turns)
            total_tokens_out = sum(r.tokens_out for r in sys_turns)
            accuracy = (
                statistics.mean(r.judge_score for r in sys_evals)
                if sys_evals else 0.0
            )

            summary[sys] = {
                "total_tokens_ingested": total_tokens_in,
                "total_tokens_retrieved": total_tokens_out,
                "store_p95_latency_s": _p95(store_latencies),
                "recall_p95_latency_s": _p95(recall_latencies),
                "overall_p95_latency_s": _p95(all_latencies),
                "retrieval_accuracy": round(accuracy, 3),
                "successful_ops": sum(1 for r in sys_turns if r.success),
                "failed_ops": sum(1 for r in sys_turns if not r.success),
                "eval_questions": len(sys_evals),
            }
        return summary


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * 0.95)
    return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 4)


# ── Memanto adapter ─────────────────────────────────────────────────────────

class MemantoAdapter:
    """
    Memanto memory adapter using official moorcheh-sdk.
    Uses MoorchehClient: namespaces, documents, similarity_search, answer.
    """

    name = "Memanto"

    def __init__(self, api_key: str, namespace: str):
        from moorcheh_sdk import MoorchehClient
        from moorcheh_sdk.types.document import Document
        self._Document = Document
        self._client = MoorchehClient(api_key=api_key)
        self.namespace = namespace
        self._setup()

    def _setup(self):
        try:
            self._client.namespaces.create(namespace_name=self.namespace, type="text")
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

    def store(self, text: str, session: int, turn: int) -> Tuple[float, int, int, bool, str]:
        """Store memory. Returns (latency, tokens_in, tokens_out, success, error)."""
        tokens_in = _count_tokens(text)
        start = time.perf_counter()
        try:
            doc: self._Document = {
                "id": str(uuid.uuid4()),
                "text": text,
                "metadata": {"session": session, "turn": turn, "type": "preference"},
            }
            self._client.documents.upload(
                namespace_name=self.namespace,
                documents=[doc],
            )
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, True, ""
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e)

    def recall(self, query: str, limit: int = 5) -> Tuple[float, int, int, bool, str, str]:
        """Recall memories. Returns (latency, tokens_in, tokens_out, success, error, answer)."""
        tokens_in = _count_tokens(query)
        start = time.perf_counter()
        try:
            response = self._client.similarity_search.query(
                namespaces=[self.namespace],
                query=query,
                top_k=limit,
            )
            items = response.results if hasattr(response, "results") else []
            texts = [
                (i.text if hasattr(i, "text") else i.get("text", ""))
                for i in items if i
            ]
            answer = "\n".join(t for t in texts if t)
            tokens_out = _count_tokens(answer)
            latency = time.perf_counter() - start
            return latency, tokens_in, tokens_out, True, "", answer
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e), ""

    def answer(self, question: str) -> Tuple[float, int, int, bool, str, str]:
        """RAG answer. Returns (latency, tokens_in, tokens_out, success, error, answer)."""
        tokens_in = _count_tokens(question)
        start = time.perf_counter()
        try:
            response = self._client.answer.generate(
                query=question,
                namespace=self.namespace,
            )
            ans = response.answer if hasattr(response, "answer") else ""
            tokens_out = _count_tokens(ans)
            latency = time.perf_counter() - start
            return latency, tokens_in, tokens_out, True, "", ans
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e), ""

    def teardown(self):
        try:
            self._client.namespaces.delete(namespace_name=self.namespace)
        except Exception:
            pass


# ── Mem0 adapter ─────────────────────────────────────────────────────────────

class Mem0Adapter:
    """
    Mem0 memory adapter.
    Uses mem0ai SDK (pip install mem0ai).
    """

    name = "Mem0"

    def __init__(self, api_key: str, user_id: str):
        from mem0 import MemoryClient
        self._client = MemoryClient(api_key=api_key)
        self.user_id = user_id

    def store(self, text: str, session: int, turn: int) -> Tuple[float, int, int, bool, str]:
        tokens_in = _count_tokens(text)
        messages = [{"role": "user", "content": text}]
        start = time.perf_counter()
        try:
            self._client.add(messages, user_id=self.user_id)
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, True, ""
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e)

    def recall(self, query: str, limit: int = 5) -> Tuple[float, int, int, bool, str, str]:
        tokens_in = _count_tokens(query)
        start = time.perf_counter()
        try:
            results = self._client.search(query, user_id=self.user_id, limit=limit)
            texts = [r.get("memory", "") for r in (results or [])]
            answer = "\n".join(t for t in texts if t)
            tokens_out = _count_tokens(answer)
            latency = time.perf_counter() - start
            return latency, tokens_in, tokens_out, True, "", answer
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e), ""

    def answer(self, question: str) -> Tuple[float, int, int, bool, str, str]:
        """Mem0 doesn't have native RAG answer — simulate with recall + format."""
        latency, ti, to, ok, err, recalled = self.recall(question)
        if not ok:
            return latency, ti, to, False, err, ""
        answer = f"Based on stored memories:\n{recalled}" if recalled else ""
        return latency, ti, to, True, "", answer

    def teardown(self):
        try:
            self._client.delete_all(user_id=self.user_id)
        except Exception:
            pass


# ── LLM Judge ────────────────────────────────────────────────────────────────

def judge_answer(
    question: str,
    system_answer: str,
    golden_answer: str,
    must_contain: List[str],
    anthropic_key: str,
) -> Tuple[float, str, int]:
    """
    LLM-as-Judge: score system answer against golden answer.
    Returns (score 0.0-1.0, reasoning, tokens_used).
    """
    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)

    must_check = ""
    if must_contain:
        must_check = f"\nThe answer SHOULD mention: {', '.join(must_contain)}"

    prompt = f"""You are an impartial judge evaluating a memory system's retrieval accuracy.

Question: {question}

Golden answer (ground truth): {golden_answer}

System answer: {system_answer or "(no answer returned)"}
{must_check}

Score the system answer from 0.0 to 1.0:
- 1.0: Fully correct, mentions all key facts
- 0.7-0.9: Mostly correct, minor omissions
- 0.4-0.6: Partially correct, misses important facts
- 0.1-0.3: Mostly wrong or very incomplete
- 0.0: Completely wrong or empty

Respond with ONLY a JSON object: {{"score": 0.0, "reasoning": "..."}}"""

    try:
        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences
        import re
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(clean)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return float(parsed["score"]), str(parsed["reasoning"]), tokens
    except Exception as e:
        return 0.0, f"judge error: {e}", 0


# ── Token counter ─────────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token)."""
    return max(1, len(text) // 4)


# ── Main benchmark ─────────────────────────────────────────────────────────────

def run_benchmark(
    skip_mem0: bool = False,
    dry_run: bool = False,
    sessions_filter: Optional[List[int]] = None,
) -> BenchmarkResults:
    moorcheh_key = os.getenv("MOORCHEH_API_KEY", "")
    mem0_key = os.getenv("MEM0_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not moorcheh_key:
        raise ValueError("MOORCHEH_API_KEY required")
    if not skip_mem0 and not mem0_key:
        print("⚠️  MEM0_API_KEY not set — running Memanto only (use --skip-mem0)")
        skip_mem0 = True
    if not anthropic_key:
        print("⚠️  ANTHROPIC_API_KEY not set — skipping LLM judge")

    conversations = json.loads((DATA_DIR / "persona_conversations.json").read_text())
    golden_qa = json.loads((DATA_DIR / "golden_qa.json").read_text())

    config = {
        "experiment_id": EXPERIMENT_ID,
        "judge_model": JUDGE_MODEL,
        "memanto_namespace": MEMANTO_NAMESPACE,
        "benchmark_scenario": "Shifting Persona & Temporal Tracking (Scenario B)",
        "dataset": "persona_conversations.json + golden_qa.json",
        "systems": ["Memanto"] + ([] if skip_mem0 else ["Mem0"]),
        "memanto_sdk": "moorcheh-sdk>=1.3.5",
        "mem0_sdk": "mem0ai>=0.1.0" if not skip_mem0 else "skipped",
        "token_counting": "approximate (len//4)",
        "sessions": sessions_filter or [1, 2, 3],
    }

    results = BenchmarkResults(experiment_id=EXPERIMENT_ID, config=config)

    if dry_run:
        print("✅ Dry run — config valid. Set env vars and run without --dry-run.")
        print(json.dumps(config, indent=2))
        return results

    # Init adapters
    print(f"\n🧪 Initializing systems...")
    memanto = MemantoAdapter(api_key=moorcheh_key, namespace=MEMANTO_NAMESPACE)
    mem0 = Mem0Adapter(api_key=mem0_key, user_id=f"benchmark-{EXPERIMENT_ID}") if not skip_mem0 else None
    adapters = [memanto] + ([mem0] if mem0 else [])
    print(f"  ✅ {[a.name for a in adapters]}")

    # Run sessions
    current_session = 0
    for conv in conversations:
        session = conv["session"]
        turn = conv["turn"]
        text = conv["user"]

        if sessions_filter and session not in sessions_filter:
            continue

        if session != current_session:
            current_session = session
            print(f"\n📅 Session {session}")

        print(f"  Turn {turn}: storing '{text[:50]}...'")

        for adapter in adapters:
            latency, ti, to, ok, err = adapter.store(text, session, turn)
            results.turn_results.append(TurnResult(
                system=adapter.name,
                session=session,
                turn=turn,
                operation="store",
                latency_s=round(latency, 4),
                tokens_in=ti,
                tokens_out=to,
                success=ok,
                error=err,
            ))
            status = "✅" if ok else "❌"
            print(f"    [{adapter.name}] {status} store {latency:.3f}s {'ERR:'+err if not ok else ''}")

        # Run eval questions for this session
        session_questions = [q for q in golden_qa if q["after_session"] == session]
        if session_questions and turn == max(c["turn"] for c in conversations if c["session"] == session):
            print(f"\n  🔍 Evaluating {len(session_questions)} questions after session {session}...")
            for qa in session_questions:
                for adapter in adapters:
                    lat, ti, to, ok, err, answer = adapter.recall(qa["question"], limit=5)
                    results.turn_results.append(TurnResult(
                        system=adapter.name,
                        session=session,
                        turn=turn,
                        operation="recall",
                        latency_s=round(lat, 4),
                        tokens_in=ti,
                        tokens_out=to,
                        success=ok,
                        error=err,
                    ))

                    score, reasoning, judge_tokens = 0.0, "no judge", 0
                    if anthropic_key and ok:
                        score, reasoning, judge_tokens = judge_answer(
                            qa["question"], answer, qa["golden_answer"],
                            qa.get("must_contain", []), anthropic_key,
                        )

                    results.eval_results.append(EvalResult(
                        question_id=qa["id"],
                        system=adapter.name,
                        after_session=session,
                        question=qa["question"],
                        system_answer=answer,
                        golden_answer=qa["golden_answer"],
                        judge_score=score,
                        judge_reasoning=reasoning,
                        latency_s=round(lat, 4),
                        tokens_used=to + judge_tokens,
                    ))
                    print(f"    [{adapter.name}] Q{qa['id']} score={score:.2f} lat={lat:.3f}s")

    # Teardown
    for adapter in adapters:
        adapter.teardown()

    return results


def print_results_table(results: BenchmarkResults):
    summary = results.summary()
    print("\n" + "=" * 70)
    print("  BENCHMARK RESULTS — Memanto vs Mem0")
    print("  Scenario B: Shifting Persona & Temporal Tracking")
    print("=" * 70)

    headers = ["Metric", *summary.keys()]
    rows = [
        ["Total Tokens Ingested", *[str(summary[s]["total_tokens_ingested"]) for s in summary]],
        ["Total Tokens Retrieved", *[str(summary[s]["total_tokens_retrieved"]) for s in summary]],
        ["Store p95 Latency (s)", *[str(summary[s]["store_p95_latency_s"]) for s in summary]],
        ["Recall p95 Latency (s)", *[str(summary[s]["recall_p95_latency_s"]) for s in summary]],
        ["Retrieval Accuracy", *[f"{summary[s]['retrieval_accuracy']:.1%}" for s in summary]],
        ["Successful Ops", *[str(summary[s]["successful_ops"]) for s in summary]],
    ]

    col_w = 30
    print(f"\n{'Metric':<{col_w}}", end="")
    for h in list(summary.keys()):
        print(f"{h:<20}", end="")
    print()
    print("-" * 70)
    for row in rows:
        print(f"{row[0]:<{col_w}}", end="")
        for cell in row[1:]:
            print(f"{cell:<20}", end="")
        print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Memanto vs Mem0 benchmark")
    parser.add_argument("--skip-mem0", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sessions", help="e.g. 1,2,3")
    args = parser.parse_args()

    sessions = [int(s) for s in args.sessions.split(",")] if args.sessions else None

    print("🏁 Memanto vs Mem0 — Shifting Persona Benchmark")
    print(f"   Experiment ID: {EXPERIMENT_ID}\n")

    results = run_benchmark(
        skip_mem0=args.skip_mem0,
        dry_run=args.dry_run,
        sessions_filter=sessions,
    )

    if not args.dry_run:
        print_results_table(results)

        # Save results
        out = RESULTS_DIR / f"{EXPERIMENT_ID}.json"
        out.write_text(json.dumps({
            "config": results.config,
            "summary": results.summary(),
            "turn_results": [asdict(r) for r in results.turn_results],
            "eval_results": [asdict(r) for r in results.eval_results],
        }, indent=2))
        print(f"\n💾 Full results saved → {out}")


if __name__ == "__main__":
    main()

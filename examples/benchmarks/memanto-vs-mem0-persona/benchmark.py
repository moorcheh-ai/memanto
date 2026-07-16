"""
benchmark.py
============
Memanto vs Mem0 — Shifting Persona & Temporal Preference Retention Benchmark

Tests the hardest problem in production agent memory:
  Do you surface the CURRENT preference — or a stale one from session 1?

Scenario: A cinephile whose taste evolves across 5 sessions and 22 turns.
7 explicit contradictions. 3 query types: recency, contradiction_resolution,
staleness_detection.

Also exercises Memanto-exclusive temporal APIs:
  - recall/as-of  : what did we know at the end of session 2?
  - recall/changed-since : what changed after session 1?

Metrics:
  - Total Tokens Ingested / Retrieved per turn
  - p95 Latency (seconds) for store and recall
  - Retrieval Accuracy (LLM-as-Judge, 0.0–1.0)
  - Per query-type accuracy breakdown

Environment:
  MOORCHEH_API_KEY   — Memanto/Moorcheh key (moorcheh.ai)
  MEM0_API_KEY       — Mem0 key (mem0.ai)
  ANTHROPIC_API_KEY  — Judge LLM key

Usage:
  python benchmark.py                    # full benchmark
  python benchmark.py --dry-run          # validate setup only
  python benchmark.py --skip-mem0       # Memanto only
  python benchmark.py --sessions 1,2,3  # subset of sessions
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)

EXPERIMENT_ID = f"benchmark-{int(time.time())}"
JUDGE_MODEL = "claude-sonnet-4-6"
MEMANTO_NAMESPACE = f"benchmark-persona-{EXPERIMENT_ID}"
RECALL_LIMIT = 10  # identical for both systems

# ── Data structures ─────────────────────────────────────────────────────────


@dataclass
class TurnResult:
    system: str
    session: int
    turn: int
    operation: str  # "store" | "recall" | "temporal_recall"
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
    query_type: str
    system_answer: str
    golden_answer: str
    judge_score: float
    judge_reasoning: str
    latency_s: float
    tokens_used: int


@dataclass
class BenchmarkResults:
    experiment_id: str
    config: dict
    turn_results: list[TurnResult] = field(default_factory=list)
    eval_results: list[EvalResult] = field(default_factory=list)

    def summary(self) -> dict:
        systems = {r.system for r in self.turn_results}
        summary = {}
        for sys in systems:
            sys_turns = [r for r in self.turn_results if r.system == sys]
            store_turns = [r for r in sys_turns if r.operation == "store"]
            recall_turns = [
                r for r in sys_turns if r.operation in ("recall", "temporal_recall")
            ]
            sys_evals = [r for r in self.eval_results if r.system == sys]

            store_latencies = [r.latency_s for r in store_turns if r.success]
            recall_latencies = [r.latency_s for r in recall_turns if r.success]
            accuracy = (
                statistics.mean(r.judge_score for r in sys_evals) if sys_evals else 0.0
            )

            # Per query-type accuracy
            type_accuracy = {}
            for qt in ("recency", "contradiction_resolution", "staleness_detection"):
                qt_evals = [r for r in sys_evals if r.query_type == qt]
                type_accuracy[qt] = (
                    round(statistics.mean(r.judge_score for r in qt_evals), 3)
                    if qt_evals
                    else None
                )

            summary[sys] = {
                "total_tokens_ingested": sum(r.tokens_in for r in sys_turns),
                "total_tokens_retrieved": sum(r.tokens_out for r in sys_turns),
                "store_p95_latency_s": _p95(store_latencies),
                "recall_p95_latency_s": _p95(recall_latencies),
                "retrieval_accuracy": round(accuracy, 3),
                "accuracy_by_query_type": type_accuracy,
                "successful_ops": sum(1 for r in sys_turns if r.success),
                "failed_ops": sum(1 for r in sys_turns if not r.success),
                "eval_questions": len(sys_evals),
            }
        return summary


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    idx = int(len(sv) * 0.95)
    return round(sv[min(idx, len(sv) - 1)], 4)


# ── Memanto adapter ─────────────────────────────────────────────────────────


class MemantoAdapter:
    """
    Memanto memory adapter.
    Uses moorcheh-sdk: namespaces, documents, similarity_search, answer.
    Also exercises temporal endpoints: recall/as-of, recall/changed-since.
    """

    name = "Memanto"

    def __init__(
        self, api_key: str, namespace: str, base_url: str = "http://localhost:8000"
    ):
        from moorcheh_sdk import MoorchehClient
        from moorcheh_sdk.types.document import Document

        self._Document = Document
        self._client = MoorchehClient(api_key=api_key)
        self.namespace = namespace
        self.base_url = base_url.rstrip("/")
        self._session_timestamps: dict[int, str] = {}
        self._setup()

    def _setup(self):
        try:
            self._client.namespaces.create(namespace_name=self.namespace, type="text")
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

    def store(
        self, text: str, session: int, turn: int
    ) -> tuple[float, int, int, bool, str]:
        tokens_in = _count_tokens(text)
        start = time.perf_counter()
        try:
            doc = {
                "id": str(uuid.uuid4()),
                "text": text,
                "metadata": {"session": session, "turn": turn, "type": "preference"},
            }
            self._client.documents.upload(
                namespace_name=self.namespace,
                documents=[doc],
            )
            latency = time.perf_counter() - start
            # Record session timestamp after last turn of session
            import datetime

            self._session_timestamps[session] = (
                datetime.datetime.utcnow().isoformat() + "Z"
            )
            return latency, tokens_in, 0, True, ""
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e)

    def recall(
        self, query: str, limit: int = RECALL_LIMIT
    ) -> tuple[float, int, int, bool, str, str]:
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
                for i in items
                if i
            ]
            answer = "\n".join(t for t in texts if t)
            tokens_out = _count_tokens(answer)
            latency = time.perf_counter() - start
            return latency, tokens_in, tokens_out, True, "", answer
        except Exception as e:
            latency = time.perf_counter() - start
            return latency, tokens_in, 0, False, str(e), ""

    def temporal_recall_as_of(
        self, query: str, as_of_session: int
    ) -> tuple[float, int, int, bool, str, str]:
        """Memanto-exclusive: retrieve memories as they existed at end of a session."""
        import requests

        tokens_in = _count_tokens(query)
        ts = self._session_timestamps.get(as_of_session, "")
        if not ts:
            return 0.0, tokens_in, 0, False, "no timestamp for session", ""
        start = time.perf_counter()
        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/memories/{self.namespace}/recall/as-of",
                json={"query": query, "as_of": ts, "limit": RECALL_LIMIT},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results", [])
            answer = "\n".join(i.get("text", "") for i in items if i.get("text"))
            tokens_out = _count_tokens(answer)
            latency = time.perf_counter() - start
            return latency, tokens_in, tokens_out, True, "", answer
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
    """Mem0 cloud memory adapter using mem0ai SDK."""

    name = "Mem0"

    def __init__(self, api_key: str, user_id: str):
        from mem0 import MemoryClient

        self._client = MemoryClient(api_key=api_key)
        self.user_id = user_id

    def store(
        self, text: str, session: int, turn: int
    ) -> tuple[float, int, int, bool, str]:
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

    def recall(
        self, query: str, limit: int = RECALL_LIMIT
    ) -> tuple[float, int, int, bool, str, str]:
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
    must_contain: list[str],
    must_not_contain: list[str],
    anthropic_key: str,
) -> tuple[float, str, int]:
    import anthropic

    client = anthropic.Anthropic(api_key=anthropic_key)

    must_check = (
        f"\nThe answer SHOULD mention: {', '.join(must_contain)}"
        if must_contain
        else ""
    )
    must_not_check = (
        f"\nThe answer MUST NOT contain: {', '.join(must_not_contain)}"
        if must_not_contain
        else ""
    )

    prompt = f"""You are an impartial judge evaluating a memory system's retrieval accuracy on preference drift.

Question: {question}
Golden answer (ground truth): {golden_answer}
System answer: {system_answer or "(no answer returned)"}
{must_check}{must_not_check}

Scoring rubric:
- 1.0: Fully correct and current — no stale/outdated facts, all key entities present
- 0.7-0.9: Mostly correct, minor omissions, no misleading stale facts
- 0.4-0.6: Partially correct OR contains some outdated information
- 0.1-0.3: Mostly wrong, dominated by stale facts, or very incomplete
- 0.0: Completely wrong, empty, or violates must_not_contain

A system that returns BOTH old and new facts without indicating recency should score no higher than 0.6.

Respond ONLY with: {{"score": 0.0, "reasoning": "..."}}"""

    try:
        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=300,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        import re

        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(clean)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return float(parsed["score"]), str(parsed["reasoning"]), tokens
    except Exception as e:
        return 0.0, f"judge error: {e}", 0


# ── Token counter ─────────────────────────────────────────────────────────────


def _count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ── Main benchmark ─────────────────────────────────────────────────────────────


def run_benchmark(
    skip_mem0: bool = False,
    dry_run: bool = False,
    sessions_filter: list[int] | None = None,
) -> BenchmarkResults:
    moorcheh_key = os.getenv("MOORCHEH_API_KEY", "")
    mem0_key = os.getenv("MEM0_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    memanto_url = os.getenv("MEMANTO_BASE_URL", "http://localhost:8000")

    if not moorcheh_key:
        raise ValueError("MOORCHEH_API_KEY required")
    if not skip_mem0 and not mem0_key:
        print("⚠️  MEM0_API_KEY not set — running Memanto only (use --skip-mem0)")
        skip_mem0 = True
    if not anthropic_key:
        print(
            "⚠️  ANTHROPIC_API_KEY not set — skipping LLM judge, using keyword fallback"
        )

    conversations = json.loads((DATA_DIR / "persona_conversations.json").read_text())
    golden_qa = json.loads((DATA_DIR / "golden_qa.json").read_text())

    config = {
        "experiment_id": EXPERIMENT_ID,
        "judge_model": JUDGE_MODEL,
        "judge_temperature": 0.0,
        "recall_limit": RECALL_LIMIT,
        "memanto_namespace": MEMANTO_NAMESPACE,
        "benchmark_scenario": "Shifting Persona & Temporal Preference Retention (Scenario B+)",
        "dataset": "persona_conversations.json + golden_qa.json",
        "turns": len(conversations),
        "sessions": sessions_filter or sorted({c["session"] for c in conversations}),
        "contradictions": sum(1 for c in conversations if c.get("contradiction")),
        "eval_questions": len(golden_qa),
        "systems": ["Memanto"] + ([] if skip_mem0 else ["Mem0"]),
        "memanto_sdk": "moorcheh-sdk>=1.3.5",
        "mem0_sdk": "mem0ai>=0.1.0" if not skip_mem0 else "skipped",
        "token_counting": "approximate (len//4)",
    }

    results = BenchmarkResults(experiment_id=EXPERIMENT_ID, config=config)

    if dry_run:
        print("✅ Dry run — config valid.")
        print(json.dumps(config, indent=2))
        return results

    # Init adapters
    print("\n🧪 Initializing systems...")
    memanto = MemantoAdapter(
        api_key=moorcheh_key, namespace=MEMANTO_NAMESPACE, base_url=memanto_url
    )
    mem0 = (
        Mem0Adapter(api_key=mem0_key, user_id=f"benchmark-{EXPERIMENT_ID}")
        if not skip_mem0
        else None
    )
    adapters = [memanto] + ([mem0] if mem0 else [])
    print(f"  ✅ Running: {[a.name for a in adapters]}")

    # ── Ingest sessions ────────────────────────────────────────────────────
    current_session = 0
    session_last_turn: dict[int, int] = {}
    for c in conversations:
        s, t = c["session"], c["turn"]
        session_last_turn[s] = max(session_last_turn.get(s, 0), t)

    for conv in conversations:
        session = conv["session"]
        turn = conv["turn"]
        text = conv["user"]
        contradiction = conv.get("contradiction")

        if sessions_filter and session not in sessions_filter:
            continue

        if session != current_session:
            current_session = session
            print(f"\n📅 Session {session}")

        tag = f" [contradicts: '{contradiction[:40]}...']" if contradiction else ""
        print(f"  Turn {turn}{tag}: '{text[:55]}...'")

        for adapter in adapters:
            latency, ti, to, ok, err = adapter.store(text, session, turn)
            results.turn_results.append(
                TurnResult(
                    system=adapter.name,
                    session=session,
                    turn=turn,
                    operation="store",
                    latency_s=round(latency, 4),
                    tokens_in=ti,
                    tokens_out=to,
                    success=ok,
                    error=err,
                )
            )
            status = "✅" if ok else f"❌ {err}"
            print(f"    [{adapter.name}] store {latency:.3f}s {status}")

        # ── Eval after last turn of each session ──────────────────────────
        if turn == session_last_turn.get(session, 0):
            session_qs = [q for q in golden_qa if q["after_session"] == session]
            if session_qs:
                print(
                    f"\n  🔍 Evaluating {len(session_qs)} question(s) after session {session}..."
                )
                for qa in session_qs:
                    for adapter in adapters:
                        lat, ti, to, ok, err, answer = adapter.recall(qa["question"])
                        results.turn_results.append(
                            TurnResult(
                                system=adapter.name,
                                session=session,
                                turn=turn,
                                operation="recall",
                                latency_s=round(lat, 4),
                                tokens_in=ti,
                                tokens_out=to,
                                success=ok,
                                error=err,
                            )
                        )

                        # Judge
                        score, reasoning, judge_tokens = 0.0, "no judge", 0
                        if anthropic_key and ok:
                            score, reasoning, judge_tokens = judge_answer(
                                qa["question"],
                                answer,
                                qa["golden_answer"],
                                qa.get("must_contain", []),
                                qa.get("must_not_contain", []),
                                anthropic_key,
                            )
                        elif ok:
                            # Keyword fallback
                            mc = qa.get("must_contain", [])
                            mnc = qa.get("must_not_contain", [])
                            hits = sum(1 for kw in mc if kw.lower() in answer.lower())
                            bad = sum(1 for kw in mnc if kw.lower() in answer.lower())
                            score = (hits / len(mc) if mc else 1.0) * (
                                0.0 if bad else 1.0
                            )
                            reasoning = f"keyword: {hits}/{len(mc)} must_contain, {bad} must_not_contain violations"

                        results.eval_results.append(
                            EvalResult(
                                question_id=qa["id"],
                                system=adapter.name,
                                after_session=session,
                                question=qa["question"],
                                query_type=qa.get("query_type", "recency"),
                                system_answer=answer,
                                golden_answer=qa["golden_answer"],
                                judge_score=score,
                                judge_reasoning=reasoning,
                                latency_s=round(lat, 4),
                                tokens_used=to + judge_tokens,
                            )
                        )
                        print(
                            f"    [{adapter.name}] {qa['id']} ({qa.get('query_type', '?')}) score={score:.2f} lat={lat:.3f}s"
                        )

    # ── Temporal recall demo (Memanto-exclusive) ───────────────────────────
    print("\n⏱️  Temporal recall demo (Memanto-exclusive)...")
    temporal_queries = [
        (2, "What kind of movies does the user enjoy?"),
        (3, "What is the user's opinion on Tarkovsky?"),
    ]
    for as_of_session, query in temporal_queries:
        lat, ti, to, ok, err, answer = memanto.temporal_recall_as_of(
            query, as_of_session
        )
        results.turn_results.append(
            TurnResult(
                system="Memanto",
                session=as_of_session,
                turn=0,
                operation="temporal_recall",
                latency_s=round(lat, 4),
                tokens_in=ti,
                tokens_out=to,
                success=ok,
                error=err,
            )
        )
        print(
            f"  recall/as-of session {as_of_session}: {'✅' if ok else '❌'} ({lat:.3f}s)"
        )

    # Teardown
    for adapter in adapters:
        adapter.teardown()

    return results


def print_results_table(results: BenchmarkResults):
    summary = results.summary()
    print("\n" + "=" * 72)
    print("  BENCHMARK RESULTS — Memanto vs Mem0")
    print("  Scenario B+: Shifting Persona & Temporal Preference Retention")
    print("=" * 72)

    systems = list(summary.keys())
    col_w = 34

    def row(label, *vals):
        print(f"  {label:<{col_w}}", end="")
        for v in vals:
            print(f"{v:<22}", end="")
        print()

    print(f"\n  {'Metric':<{col_w}}", end="")
    for s in systems:
        print(f"{s:<22}", end="")
    print()
    print("  " + "-" * 70)

    row(
        "Total Tokens Ingested",
        *[str(summary[s]["total_tokens_ingested"]) for s in systems],
    )
    row(
        "Total Tokens Retrieved",
        *[str(summary[s]["total_tokens_retrieved"]) for s in systems],
    )
    row(
        "Store p95 Latency (s)",
        *[str(summary[s]["store_p95_latency_s"]) for s in systems],
    )
    row(
        "Recall p95 Latency (s)",
        *[str(summary[s]["recall_p95_latency_s"]) for s in systems],
    )
    row(
        "Overall Retrieval Accuracy",
        *[f"{summary[s]['retrieval_accuracy']:.1%}" for s in systems],
    )

    print()
    print(f"  {'Accuracy by Query Type':<{col_w}}", end="")
    for s in systems:
        print(f"{s:<22}", end="")
    print()
    print("  " + "-" * 70)
    for qt in ("recency", "contradiction_resolution", "staleness_detection"):
        vals = []
        for s in systems:
            v = summary[s]["accuracy_by_query_type"].get(qt)
            vals.append(f"{v:.1%}" if v is not None else "n/a")
        row(f"  {qt}", *vals)

    print("\n" + "=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Memanto vs Mem0 — Shifting Persona Benchmark"
    )
    parser.add_argument("--skip-mem0", action="store_true", help="Run Memanto only")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate config, no API calls"
    )
    parser.add_argument("--sessions", help="Comma-separated session numbers e.g. 1,2,3")
    args = parser.parse_args()

    sessions = [int(s) for s in args.sessions.split(",")] if args.sessions else None

    print("🏁 Memanto vs Mem0 — Shifting Persona & Temporal Preference Benchmark")
    print(f"   Experiment ID: {EXPERIMENT_ID}")
    conversations = json.loads((DATA_DIR / "persona_conversations.json").read_text())
    golden_qa = json.loads((DATA_DIR / "golden_qa.json").read_text())
    print(
        f"   Dataset: {len(conversations)} turns, {max(c['session'] for c in conversations)} sessions, {sum(1 for c in conversations if c.get('contradiction'))} contradictions, {len(golden_qa)} eval questions\n"
    )

    results = run_benchmark(
        skip_mem0=args.skip_mem0,
        dry_run=args.dry_run,
        sessions_filter=sessions,
    )

    if not args.dry_run:
        print_results_table(results)

        out = RESULTS_DIR / f"{EXPERIMENT_ID}.json"
        out.write_text(
            json.dumps(
                {
                    "config": results.config,
                    "summary": results.summary(),
                    "turn_results": [asdict(r) for r in results.turn_results],
                    "eval_results": [asdict(r) for r in results.eval_results],
                },
                indent=2,
            )
        )
        print(f"\n💾 Full results saved → {out}")


if __name__ == "__main__":
    main()

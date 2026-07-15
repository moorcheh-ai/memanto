"""
Benchmark harness.

Drives both memory adapters through the Executive Shadow scenario:
  1. Setup each system
  2. Ingest all sessions in order (identical input for both)
  3. Run all evaluation queries against each system
  4. Score each answer with the LLM judge
  5. Collect latency and token metrics
  6. Return a BenchmarkResult for reporting

Usage:
    from harness import run_benchmark
    result = run_benchmark()
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adapters import IngestResult, MemantoAdapter, MemoryAdapter, RecallResult
from adapters.mem0_adapter import Mem0Adapter
from evaluator import EvalScore, LLMJudge

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent / "data" / "executive_shadow.json"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class SystemResult:
    """All results for one memory system."""

    system: str
    ingest_results: list[IngestResult] = field(default_factory=list)
    recall_results: list[RecallResult] = field(default_factory=list)
    eval_scores: list[EvalScore] = field(default_factory=list)

    # ── computed metrics ──────────────────────────────────────────────────

    @property
    def total_tokens_ingested(self) -> int:
        return sum(r.tokens_ingested for r in self.ingest_results)

    @property
    def total_tokens_recalled(self) -> int:
        return sum(r.tokens_used for r in self.recall_results)

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_ingested + self.total_tokens_recalled

    @property
    def ingest_latencies(self) -> list[float]:
        return [r.latency_s for r in self.ingest_results]

    @property
    def recall_latencies(self) -> list[float]:
        return [r.latency_s for r in self.recall_results]

    @property
    def p95_ingest_latency(self) -> float:
        lats = sorted(self.ingest_latencies)
        if not lats:
            return 0.0
        idx = max(0, math.ceil(len(lats) * 0.95) - 1)
        return lats[idx]

    @property
    def p95_recall_latency(self) -> float:
        lats = sorted(self.recall_latencies)
        if not lats:
            return 0.0
        idx = max(0, math.ceil(len(lats) * 0.95) - 1)
        return lats[idx]

    @property
    def mean_recall_latency(self) -> float:
        lats = self.recall_latencies
        return statistics.mean(lats) if lats else 0.0

    @property
    def total_accuracy_score(self) -> int:
        return sum(s.accuracy for s in self.eval_scores)

    @property
    def total_staleness_score(self) -> int:
        return sum(s.staleness_avoidance for s in self.eval_scores)

    @property
    def total_precision_score(self) -> int:
        return sum(s.precision for s in self.eval_scores)

    @property
    def total_eval_score(self) -> int:
        return sum(s.total for s in self.eval_scores)

    @property
    def max_possible_eval_score(self) -> int:
        return len(self.eval_scores) * 15

    @property
    def eval_score_pct(self) -> float:
        mx = self.max_possible_eval_score
        return (self.total_eval_score / mx * 100) if mx else 0.0


@dataclass
class BenchmarkResult:
    """Final results for the full benchmark run."""

    scenario_title: str
    systems: dict[str, SystemResult]
    judge_model: str
    run_timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def winner(self) -> str:
        """Return the name of the system with the highest eval score."""
        return max(self.systems, key=lambda k: self.systems[k].total_eval_score)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def run_benchmark(
    memanto_api_key: str | None = None,
    mem0_api_key: str | None = None,
    judge_api_key: str | None = None,
    judge_model: str | None = None,
    skip_judge: bool = False,
) -> BenchmarkResult:
    """
    Run the full benchmark and return a BenchmarkResult.

    Args:
        memanto_api_key:  Overrides MOORCHEH_API_KEY env var.
        mem0_api_key:     Overrides MEM0_API_KEY env var.
        judge_api_key:    Overrides OPENROUTER_API_KEY env var.
        judge_model:      LLM model for the judge (e.g. 'anthropic/claude-3-5-haiku').
        skip_judge:       If True, skip LLM scoring (only collect latency/token metrics).
    """
    # Load scenario
    with open(DATA_FILE, encoding="utf-8") as f:
        scenario = json.load(f)

    title = scenario["title"]
    user_id = scenario["user_id"]
    sessions = scenario["sessions"]
    eval_queries = scenario["evaluation_queries"]
    meta = scenario["metadata"]

    run_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Instantiate adapters
    adapters: list[MemoryAdapter] = [
        MemantoAdapter(api_key=memanto_api_key),
        Mem0Adapter(api_key=mem0_api_key),
    ]

    # Instantiate judge
    judge: LLMJudge | None = None
    if not skip_judge:
        judge = LLMJudge(api_key=judge_api_key, model=judge_model)

    results: dict[str, SystemResult] = {}

    for adapter in adapters:
        sname = adapter.name
        logger.info("=" * 60)
        logger.info("Running %s", sname)
        logger.info("=" * 60)
        sr = SystemResult(system=sname)

        # ── Setup ─────────────────────────────────────────────────────────
        logger.info("[%s] Setting up...", sname)
        adapter.setup(user_id)

        try:
            # ── Ingest all sessions ───────────────────────────────────────
            logger.info("[%s] Ingesting %d sessions...", sname, len(sessions))
            for session in sessions:
                logger.info("[%s] Ingesting %s", sname, session["label"])
                result = adapter.ingest_session(
                    user_id=user_id,
                    session_id=session["id"],
                    messages=session["messages"],
                )
                sr.ingest_results.append(result)
                logger.info(
                    "[%s] %s → %.2fs, %d tokens",
                    sname,
                    session["id"],
                    result.latency_s,
                    result.tokens_ingested,
                )
                # Small pause between sessions to respect rate limits
                time.sleep(0.5)

            # Brief wait for indexing before recall
            logger.info("[%s] Waiting for memory indexing...", sname)
            if hasattr(adapter, "wait_for_indexing"):
                # Mem0 Platform is async — poll until memories are visible
                count = adapter.wait_for_indexing(timeout_s=60, poll_interval_s=4)
                logger.info("[%s] %d memories indexed", sname, count)
            else:
                time.sleep(3)

            # ── Recall all queries ────────────────────────────────────────
            logger.info(
                "[%s] Running %d evaluation queries...", sname, len(eval_queries)
            )
            for eq in eval_queries:
                logger.info("[%s] Query: %s", sname, eq["id"])
                recall = adapter.recall(
                    user_id=user_id,
                    query_id=eq["id"],
                    query=eq["query"],
                )
                sr.recall_results.append(recall)
                logger.info(
                    "[%s] %s → %.2fs, %d tokens, %d memories",
                    sname,
                    eq["id"],
                    recall.latency_s,
                    recall.tokens_used,
                    len(recall.memories_returned),
                )
                time.sleep(0.3)

            # ── Score with judge ──────────────────────────────────────────
            if judge:
                logger.info("[%s] Scoring with LLM judge (%s)...", sname, judge.model)
                recall_by_id = {r.query_id: r for r in sr.recall_results}
                for eq in eval_queries:
                    recalled = recall_by_id.get(eq["id"])
                    recalled_text = recalled.answer if recalled else ""
                    score = judge.score(
                        system_name=sname,
                        query_id=eq["id"],
                        query=eq["query"],
                        golden_answer=eq["golden_answer"],
                        stale_signals=eq["stale_signals"],
                        current_signals=eq["current_signals"],
                        recalled_answer=recalled_text,
                    )
                    sr.eval_scores.append(score)
                    logger.info(
                        "[%s] %s → acc=%d stale=%d prec=%d total=%d",
                        sname,
                        eq["id"],
                        score.accuracy,
                        score.staleness_avoidance,
                        score.precision,
                        score.total,
                    )
                    time.sleep(0.5)

        finally:
            # ── Teardown ──────────────────────────────────────────────────
            logger.info("[%s] Tearing down...", sname)
            adapter.teardown(user_id)

        results[sname] = sr
        logger.info("[%s] Done.", sname)

    return BenchmarkResult(
        scenario_title=title,
        systems=results,
        judge_model=judge.model if judge else "none",
        run_timestamp=run_ts,
        metadata=meta,
    )

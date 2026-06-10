"""
Scenario B: Shifting Persona & Temporal Tracking Test

Simulates an evolving user with dynamically changing preferences.
Measures preference retention accuracy and temporal awareness.

Goal: Test if Memanto effectively flags out-of-date states and surfaces
current nuances without polluting the active context window.
"""

import json
from pathlib import Path
from .base import MemoryAdapter, BenchmarkMetric
from .evaluator import LLMEvaluator


DATASET_PATH = Path(__file__).parent.parent / "datasets" / "persona_evolution.json"


def load_dataset() -> list[dict]:
    """Load the persona evolution dataset."""
    with open(DATASET_PATH) as f:
        return json.load(f)


def run_scenario_b(
    adapter: MemoryAdapter,
    evaluator: LLMEvaluator,
    user_id: str = "benchmark_user_b",
    dry_run: bool = False,
) -> BenchmarkMetric:
    """Run Scenario B against a memory adapter.

    Simulates multiple sessions where user preferences evolve and contradict.
    After ingestion, tests whether the system surfaces the LATEST preferences.

    Args:
        adapter: The memory framework adapter to test.
        evaluator: LLM judge for scoring retrieval accuracy.
        user_id: Unique user ID for this benchmark run.
        dry_run: If True, use mock data instead of real API calls.

    Returns:
        BenchmarkMetric with aggregated results.
    """
    dataset = load_dataset()
    metrics = BenchmarkMetric(
        framework=adapter.name,
        scenario="B: Shifting Persona & Temporal Tracking",
    )

    if not dry_run:
        adapter.setup(user_id)

    try:
        # Phase 1: Ingest persona evolution across sessions
        for session in dataset:
            session_id = session["session_id"]
            messages = session["messages"]

            for msg in messages:
                content = msg["content"]
                metadata = {
                    "session_id": session_id,
                    "timestamp": msg.get("timestamp", ""),
                    "role": msg.get("role", "user"),
                }

                if dry_run:
                    latency = 45.0
                    tokens = len(content.split()) * 2
                    success = True
                else:
                    latency, result = adapter.timed_call(
                        adapter.store, content, metadata
                    )
                    success = result.success
                    tokens = result.tokens_used
                    if not success:
                        metrics.errors += 1
                        continue

                metrics.total_store_calls += 1
                metrics.total_store_tokens += tokens
                metrics.store_latencies.append(latency)

        # Phase 2: Query for current preferences (should get latest)
        for session in dataset:
            for query_item in session.get("evaluation_queries", []):
                query = query_item["query"]
                golden = query_item["golden_answer"]

                if dry_run:
                    latency = 25.0
                    tokens = 150
                    retrieved_texts = ["[mock current preference]"]
                    success = True
                else:
                    latency, result = adapter.timed_call(adapter.retrieve, query)
                    success = result.success
                    tokens = result.tokens_used
                    if not success:
                        metrics.errors += 1
                        continue
                    retrieved = result.data or []
                    retrieved_texts = [
                        str(m) if not isinstance(m, dict)
                        else m.get("memory", m.get("text", str(m)))
                        for m in retrieved
                    ]

                metrics.total_retrieve_calls += 1
                metrics.total_retrieve_tokens += tokens
                metrics.retrieve_latencies.append(latency)

                score, _ = evaluator.score_retrieval(query, golden, retrieved_texts)
                metrics.retrieval_scores.append(score)

    finally:
        if not dry_run:
            adapter.cleanup()

    return metrics

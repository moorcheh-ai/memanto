"""
Scenario A: Context-Overhead & Latency Sprint

Feeds dense, shifting technical logs into each memory framework.
Measures token consumption per conversation turn and retrieval latency.

Goal: Test if Memanto's active compression prevents massive token inflation
and post-ingestion delays seen in graph-based memory systems.
"""

import json
import os
from pathlib import Path
from .base import MemoryAdapter, BenchmarkMetric
from .evaluator import LLMEvaluator


DATASET_PATH = Path(__file__).parent.parent / "datasets" / "technical_logs.json"


def load_dataset() -> list[dict]:
    """Load the technical logs dataset."""
    with open(DATASET_PATH) as f:
        return json.load(f)


def run_scenario_a(
    adapter: MemoryAdapter,
    evaluator: LLMEvaluator,
    user_id: str = "benchmark_user_a",
    dry_run: bool = False,
) -> BenchmarkMetric:
    """Run Scenario A against a memory adapter.

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
        scenario="A: Context-Overhead & Latency Sprint",
    )

    if not dry_run:
        adapter.setup(user_id)

    try:
        # Phase 1: Ingestion — store all log entries
        for entry in dataset:
            content = entry["content"]
            metadata = entry.get("metadata", {})

            if dry_run:
                latency = 50.0
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

        # Phase 2: Retrieval — query for specific information
        queries = [
            q for entry in dataset
            for q in entry.get("retrieval_queries", [])
        ]
        if not queries:
            queries = [entry["content"][:100] for entry in dataset[:5]]

        for query_item in queries:
            if isinstance(query_item, dict):
                query = query_item.get("query", "")
                golden = query_item.get("golden_answer", "")
            else:
                query = str(query_item)
                golden = ""

            if dry_run:
                latency = 30.0
                tokens = 200
                retrieved_texts = ["[mock retrieved memory]"]
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

            if golden:
                score, _ = evaluator.score_retrieval(query, golden, retrieved_texts)
                metrics.retrieval_scores.append(score)

    finally:
        if not dry_run:
            adapter.cleanup()

    return metrics

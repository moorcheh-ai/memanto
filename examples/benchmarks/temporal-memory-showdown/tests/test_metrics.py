from __future__ import annotations

from pathlib import Path

from backends import (
    MeteredOllamaClient,
    SearchHit,
    build_mem0_config,
    create_memanto_agent,
)
from dataset import QUERIES, RECORDS, QueryCase
from metrics import paired_bootstrap_delta, percentile, score_query, summarize_scores
from run_benchmark import render_markdown, run_backend


def test_dataset_shape_and_ids_are_stable():
    assert len(RECORDS) == 32
    assert len(QUERIES) == 18
    assert len({record.record_id for record in RECORDS}) == len(RECORDS)
    assert len({query.query_id for query in QUERIES}) == len(QUERIES)


def test_score_requires_all_concepts_and_penalizes_stale_context():
    case = QueryCase(
        "T1",
        "multi-hop",
        "current state",
        (("alpha",), ("beta", "bravo")),
        (("legacy",),),
    )
    clean = score_query(case, "Alpha and bravo are active.")
    assert clean.coverage == 1.0
    assert clean.exact is True
    assert clean.stale_leak is False

    stale = score_query(case, "Alpha and beta are active; legacy remains.")
    assert stale.coverage == 1.0
    assert stale.exact is False
    assert stale.stale_leak is True


def test_percentile_uses_nearest_rank():
    assert percentile([1, 2, 3, 4, 5], 0.95) == 5
    assert percentile([1, 2, 3, 4, 5], 0.50) == 3
    assert percentile([], 0.95) == 0.0


def test_summary_groups_categories():
    current = score_query(QUERIES[0], "Dwarf radish is current.")
    historical = score_query(QUERIES[11], "Genovese basil was first.")
    summary = summarize_scores([current, historical])
    assert summary["mean_coverage"] == 1.0
    assert summary["exact_accuracy"] == 1.0
    assert set(summary["by_category"]) == {"current-state", "historical"}


def test_bootstrap_is_deterministic():
    baseline = [score_query(QUERIES[0], "basil") for _ in range(4)]
    challenger = [score_query(QUERIES[0], "dwarf radish") for _ in range(4)]
    result = paired_bootstrap_delta(baseline, challenger, samples=100, seed=123)
    assert result["observed_delta"] == 1.0
    assert result["ci95"] == [1.0, 1.0]


def test_mem0_config_matches_installed_schema(tmp_path: Path):
    from mem0.configs.base import MemoryConfig

    config = build_mem0_config(
        ollama_url="http://127.0.0.1:11434",
        llm_model="qwen2.5:1.5b",
        run_id="test",
        backend_name="mem0-direct",
        work_dir=tmp_path,
    )
    parsed = MemoryConfig(**config)
    assert parsed.llm.provider == "ollama"
    assert parsed.embedder.config["embedding_dims"] == 768
    assert parsed.vector_store.config.collection_name.startswith("temporal_test")


def test_ollama_meter_reads_native_token_counts():
    class FakeClient:
        def chat(self, *args, **kwargs):
            return {"prompt_eval_count": 17, "eval_count": 5, "message": {}}

    meter = MeteredOllamaClient(FakeClient())
    meter.chat(model="test", messages=[])
    assert meter.calls == 1
    assert meter.input_tokens == 17
    assert meter.output_tokens == 5


def test_memanto_agent_bootstrap_retries_idempotently():
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def create_agent(self, **kwargs):
            self.calls += 1
            assert kwargs["agent_id"] == "bench-test"
            if self.calls == 1:
                raise RuntimeError("namespace committed before server returned 500")

    client = FlakyClient()
    create_memanto_agent(
        client,
        agent_id="bench-test",
        pattern="tool",
        description="benchmark",
        attempts=2,
        delay_s=0,
    )
    assert client.calls == 2


def test_runner_produces_auditable_report_shape():
    class FakeBackend:
        name = "fake"

        def __init__(self):
            self.records = []

        def ingest(self, record):
            self.records.append(record)

        def search(self, query, top_k):
            text = "\n".join(record.text for record in self.records)
            return [SearchHit(text=text)]

        def usage(self):
            return {
                "llm_calls": 0,
                "llm_input_tokens": 0,
                "llm_output_tokens": 0,
            }

        def close(self):
            return None

    result = run_backend(
        FakeBackend(),
        top_k=5,
        repeats=2,
        ready_timeout=1.0,
    )
    assert result["metrics"]["records_ingested"] == len(RECORDS)
    assert result["metrics"]["queries_evaluated"] == len(QUERIES)
    assert len(result["queries"]) == len(QUERIES)

    report = {
        "environment": {"timestamp_utc": "2026-06-13T00:00:00+00:00"},
        "runs": [result],
    }
    markdown = render_markdown(report)
    assert "Temporal Memory Showdown Results" in markdown
    assert "| fake |" in markdown

from __future__ import annotations

import pathlib
import sys

BENCHMARK_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_ROOT))

from incident_memory_pressure.backends import MemantoTypedDigestBackend
from incident_memory_pressure.dataset import IncidentQuery
from incident_memory_pressure.runner import run_benchmark
from incident_memory_pressure.runner import _evaluate_backend


def test_memanto_style_backend_uses_less_context_than_append_only() -> None:
    """The typed digest should retrieve less context than the append-only log."""

    report = run_benchmark()
    results = {result.backend: result for result in report.results}

    memanto = results["memanto_typed_digest"]
    append_only = results["append_only_log"]

    assert memanto.tokens_ingested == append_only.tokens_ingested
    assert memanto.tokens_retrieved < append_only.tokens_retrieved


def test_memanto_style_backend_suppresses_stale_facts() -> None:
    """The typed digest should suppress stale facts better than the baseline."""

    report = run_benchmark()
    results = {result.backend: result for result in report.results}

    memanto = results["memanto_typed_digest"]
    append_only = results["append_only_log"]

    assert memanto.stale_suppression == 1.0
    assert memanto.retrieval_accuracy > append_only.retrieval_accuracy


def test_report_outputs_are_stable() -> None:
    """JSON and Markdown report outputs should include expected stable labels."""

    report = run_benchmark()

    json_output = report.to_json()
    markdown_output = report.to_markdown()

    assert "memanto_typed_digest" in json_output
    assert "append_only_log" in markdown_output
    assert "| Backend | Tokens Ingested |" in markdown_output


def test_empty_scoring_fragments_do_not_crash() -> None:
    """A query with no scoring fragments should produce defensive metrics."""

    backend = MemantoTypedDigestBackend()
    backend.ingest([])

    result, traces = _evaluate_backend(
        backend,
        records=[],
        queries=[
            IncidentQuery(
                service="empty",
                prompt="What should be recalled?",
                expected_fragments=(),
                stale_fragments=(),
            )
        ],
    )

    assert result.retrieval_accuracy == 0.0
    assert result.stale_suppression == 1.0
    assert traces[0].expected_hits == 0
    assert traces[0].stale_hits == 0


if __name__ == "__main__":
    test_memanto_style_backend_uses_less_context_than_append_only()
    test_memanto_style_backend_suppresses_stale_facts()
    test_report_outputs_are_stable()
    test_empty_scoring_fragments_do_not_crash()

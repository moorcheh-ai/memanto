from __future__ import annotations

import pathlib
import sys

BENCHMARK_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_ROOT))

from incident_memory_pressure.runner import run_benchmark


def test_memanto_style_backend_uses_less_context_than_append_only() -> None:
    report = run_benchmark()
    results = {result.backend: result for result in report.results}

    memanto = results["memanto_typed_digest"]
    append_only = results["append_only_log"]

    assert memanto.tokens_ingested == append_only.tokens_ingested
    assert memanto.tokens_retrieved < append_only.tokens_retrieved


def test_memanto_style_backend_suppresses_stale_facts() -> None:
    report = run_benchmark()
    results = {result.backend: result for result in report.results}

    memanto = results["memanto_typed_digest"]
    append_only = results["append_only_log"]

    assert memanto.stale_suppression == 1.0
    assert memanto.retrieval_accuracy > append_only.retrieval_accuracy


def test_report_outputs_are_stable() -> None:
    report = run_benchmark()

    json_output = report.to_json()
    markdown_output = report.to_markdown()

    assert "memanto_typed_digest" in json_output
    assert "append_only_log" in markdown_output
    assert "| Backend | Tokens Ingested |" in markdown_output


if __name__ == "__main__":
    test_memanto_style_backend_uses_less_context_than_append_only()
    test_memanto_style_backend_suppresses_stale_facts()
    test_report_outputs_are_stable()

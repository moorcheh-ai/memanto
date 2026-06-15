"""Tests for the incident runbook memory benchmark."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_benchmark_module():
    """Load the sibling benchmark runner as an importable module."""

    module_path = Path(__file__).with_name("run_benchmark.py")
    if not module_path.exists():
        raise AssertionError("run_benchmark module is missing")

    spec = importlib.util.spec_from_file_location("run_benchmark", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("run_benchmark module cannot be loaded")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        raise AssertionError("run_benchmark has a missing dependency") from exc
    return module


class IncidentRunbookBenchmarkTests(unittest.TestCase):
    """Regression tests for the incident runbook memory benchmark."""

    def test_active_digest_outperforms_log_baseline(self) -> None:
        """The active digest should beat the append-only control."""

        benchmark = load_benchmark_module()

        result = benchmark.run_benchmark()
        backends = {row["backend"]: row for row in result["metrics"]}

        self.assertIn("active_incident_digest", backends)
        self.assertIn("append_only_log", backends)

        active = backends["active_incident_digest"]
        append_only = backends["append_only_log"]

        self.assertGreater(active["retrieval_accuracy"], append_only["retrieval_accuracy"])
        self.assertLess(active["avg_retrieved_tokens"], append_only["avg_retrieved_tokens"])
        self.assertEqual(active["stale_conflict_rate"], 0.0)
        self.assertEqual(active["secret_leak_rate"], 0.0)

    def test_recent_window_misses_older_still_current_facts(self) -> None:
        """Recent-only memory should miss an older still-current fact."""

        benchmark = load_benchmark_module()

        result = benchmark.run_benchmark()
        backends = {row["backend"]: row for row in result["metrics"]}

        self.assertIn("recent_window_log", backends)
        self.assertLess(
            backends["recent_window_log"]["retrieval_accuracy"],
            backends["active_incident_digest"]["retrieval_accuracy"],
        )

    def test_report_writers_create_json_and_markdown(self) -> None:
        """Report writers should create readable JSON and Markdown artifacts."""

        benchmark = load_benchmark_module()
        result = benchmark.run_benchmark()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result_dir = Path(tmp_dir)
            json_path = result_dir / "test_results.json"
            md_path = result_dir / "test_results.md"

            benchmark.write_json(result, json_path)
            benchmark.write_markdown(result, md_path)

            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(parsed["benchmark"], "incident-runbook-memory")
        self.assertIn("| Backend | Retrieval accuracy |", markdown)
        self.assertIn("active_incident_digest", markdown)


if __name__ == "__main__":
    unittest.main()

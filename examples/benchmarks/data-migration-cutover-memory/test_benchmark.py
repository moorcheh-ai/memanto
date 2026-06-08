"""Tests for the data migration cutover memory benchmark."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_benchmark


class DataMigrationCutoverBenchmarkTest(unittest.TestCase):
    def test_dataset_loads_with_expected_shape(self) -> None:
        dataset = run_benchmark.load_dataset()

        self.assertEqual(dataset.name, "billing-data-migration-cutover-v1")
        self.assertEqual(dataset.session_count, 5)
        self.assertEqual(len(dataset.events), 20)
        self.assertEqual(len(dataset.probes), 8)
        event_by_id = {event.id: event for event in dataset.events}
        self.assertIn("E01", event_by_id["E13"].supersedes)

    def test_active_digest_scores_best_on_current_state(self) -> None:
        report = run_benchmark.run_benchmark()
        by_backend = {item["backend"]: item["summary"] for item in report["results"]}

        active = by_backend["memanto_active_digest"]
        append_only = by_backend["passive_append_only"]
        recent = by_backend["recent_window"]

        self.assertGreaterEqual(active["retrieval_accuracy"], 0.95)
        self.assertGreater(
            active["retrieval_accuracy"], append_only["retrieval_accuracy"]
        )
        self.assertGreater(active["retrieval_accuracy"], recent["retrieval_accuracy"])
        self.assertEqual(active["stale_conflict_rate"], 0.0)
        self.assertGreater(append_only["stale_conflict_rate"], 0.0)
        self.assertEqual(active["sensitive_leak_rate"], 0.0)
        self.assertGreater(append_only["sensitive_leak_rate"], 0.0)
        self.assertLess(
            active["stored_memory_tokens"], append_only["stored_memory_tokens"]
        )

    def test_sensitive_probe_redacts_secret_for_active_digest(self) -> None:
        report = run_benchmark.run_benchmark()
        active = next(
            item
            for item in report["results"]
            if item["backend"] == "memanto_active_digest"
        )
        sensitive_probe = next(
            item for item in active["probe_results"] if item["probe_id"] == "P05"
        )

        self.assertEqual(sensitive_probe["sensitive_leak_terms"], [])
        self.assertEqual(sensitive_probe["matched_expected_evidence"], ["E09"])

    def test_reports_are_written(self) -> None:
        report = run_benchmark.run_benchmark()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_path = tmp / "report.json"
            markdown_path = tmp / "report.md"

            run_benchmark.write_json_report(report, json_path)
            run_benchmark.write_markdown_report(report, markdown_path)

            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertEqual(parsed["benchmark"]["name"], run_benchmark.BENCHMARK_NAME)
            self.assertIn("| memanto_active_digest |", markdown)
            self.assertIn("Data Migration Cutover Memory Benchmark", markdown)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "policy_drift_memory_benchmark",
    ROOT / "run_benchmark.py",
)
assert SPEC is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


def backend_by_name(report: dict, name: str) -> dict:
    return next(backend for backend in report["backends"] if backend["name"] == name)


class PolicyDriftBenchmarkTest(unittest.TestCase):
    def test_active_digest_retrieves_current_policy_state(self) -> None:
        report = benchmark.run_benchmark()
        active = backend_by_name(report, "memanto_active_digest")

        self.assertEqual(active["metrics"]["passed_queries"], 8)
        self.assertEqual(active["metrics"]["accuracy"], 1.0)
        self.assertEqual(active["metrics"]["stale_conflict_rate"], 0.0)
        self.assertEqual(active["metrics"]["sensitive_leak_rate"], 0.0)

    def test_passive_append_only_baseline_exposes_stale_sensitive_facts(self) -> None:
        report = benchmark.run_benchmark()
        append_only = backend_by_name(report, "append_only_log")

        self.assertLess(append_only["metrics"]["accuracy"], 1.0)
        self.assertGreater(append_only["metrics"]["stale_conflict_rate"], 0.0)
        self.assertGreater(append_only["metrics"]["sensitive_leak_rate"], 0.0)

    def test_recent_window_baseline_misses_older_current_facts(self) -> None:
        report = benchmark.run_benchmark()
        active = backend_by_name(report, "memanto_active_digest")
        recent = backend_by_name(report, "recent_window_log")

        self.assertLess(recent["metrics"]["accuracy"], active["metrics"]["accuracy"])
        self.assertLess(
            recent["metrics"]["stored_tokens_after_ingest"],
            active["metrics"]["stored_tokens_after_ingest"],
        )

    def test_report_is_deterministic(self) -> None:
        self.assertEqual(benchmark.run_benchmark(), benchmark.run_benchmark())

    def test_markdown_contains_all_backends(self) -> None:
        markdown = benchmark.format_markdown(benchmark.run_benchmark())

        self.assertIn("memanto_active_digest", markdown)
        self.assertIn("append_only_log", markdown)
        self.assertIn("recent_window_log", markdown)


if __name__ == "__main__":
    unittest.main()

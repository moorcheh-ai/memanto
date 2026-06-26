from __future__ import annotations

import importlib.util
import sys
import tempfile
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
    for backend in report["backends"]:
        if backend["name"] == name:
            return backend
    raise ValueError(f"Backend not found: {name}")


class PolicyDriftBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = benchmark.run_benchmark()

    def test_active_digest_retrieves_current_policy_state(self) -> None:
        active = backend_by_name(self.report, "memanto_active_digest")

        self.assertEqual(active["metrics"]["passed_queries"], 8)
        self.assertEqual(active["metrics"]["accuracy"], 1.0)
        self.assertEqual(active["metrics"]["stale_conflict_rate"], 0.0)
        self.assertEqual(active["metrics"]["sensitive_leak_rate"], 0.0)

    def test_passive_append_only_baseline_exposes_stale_sensitive_facts(self) -> None:
        append_only = backend_by_name(self.report, "append_only_log")

        self.assertLess(append_only["metrics"]["accuracy"], 1.0)
        self.assertGreater(append_only["metrics"]["stale_conflict_rate"], 0.0)
        self.assertGreater(append_only["metrics"]["sensitive_leak_rate"], 0.0)

    def test_recent_window_baseline_misses_older_current_facts(self) -> None:
        active = backend_by_name(self.report, "memanto_active_digest")
        recent = backend_by_name(self.report, "recent_window_log")

        self.assertLess(recent["metrics"]["accuracy"], active["metrics"]["accuracy"])
        self.assertLess(
            recent["metrics"]["stored_tokens_after_ingest"],
            active["metrics"]["stored_tokens_after_ingest"],
        )

    def test_report_is_deterministic(self) -> None:
        report_a = benchmark.run_benchmark()
        report_b = benchmark.run_benchmark()

        self.assertEqual(report_a["benchmark"], report_b["benchmark"])
        self.assertEqual(report_a["version"], report_b["version"])
        self.assertEqual(report_a["dataset"], report_b["dataset"])

        self.assertEqual(len(report_a["backends"]), len(report_b["backends"]))
        for index, backend_a in enumerate(report_a["backends"]):
            backend_b = report_b["backends"][index]
            self.assertEqual(backend_a["name"], backend_b["name"])
            self.assertEqual(backend_a["description"], backend_b["description"])
            self.assertEqual(backend_a["queries"], backend_b["queries"])
            self.assertEqual(
                backend_a["metrics"].keys(),
                backend_b["metrics"].keys(),
            )
            for key, value_a in backend_a["metrics"].items():
                value_b = backend_b["metrics"][key]
                if isinstance(value_a, float):
                    self.assertAlmostEqual(value_a, value_b, places=10)
                else:
                    self.assertEqual(value_a, value_b)

    def test_markdown_contains_all_backends(self) -> None:
        markdown = benchmark.format_markdown(self.report)

        self.assertIn("memanto_active_digest", markdown)
        self.assertIn("append_only_log", markdown)
        self.assertIn("recent_window_log", markdown)

    def test_custom_dataset_paths_are_reported_without_root_relative_crash(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            events_path = temp_path / "events.json"
            queries_path = temp_path / "queries.json"
            events_path.write_text(
                benchmark.DEFAULT_EVENTS.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            queries_path.write_text(
                benchmark.DEFAULT_QUERIES.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            report = benchmark.run_benchmark(events_path, queries_path)

        self.assertEqual(report["dataset"]["source_events"], str(events_path))
        self.assertEqual(report["dataset"]["source_queries"], str(queries_path))


if __name__ == "__main__":
    unittest.main()

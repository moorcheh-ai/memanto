import json
import tempfile
import unittest
from pathlib import Path

import run_benchmark


class ChangeControlBenchmarkTests(unittest.TestCase):
    def test_redacts_synthetic_secrets(self) -> None:
        text = "token=abc123 password=super-secret owner=noah"
        redacted = run_benchmark.redact(text)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("super-secret", redacted)
        self.assertIn("token=[REDACTED]", redacted)
        self.assertIn("password=[REDACTED]", redacted)

    def test_active_digest_beats_append_only_on_current_facts(self) -> None:
        report = run_benchmark.run_benchmark()
        summaries = {summary["backend"]: summary for summary in report["summaries"]}
        active = summaries["active_change_digest"]
        append_only = summaries["append_only_log"]

        self.assertGreater(active["accuracy"], append_only["accuracy"])
        self.assertEqual(active["secret_leak_rate"], 0.0)
        self.assertGreater(append_only["stale_conflict_rate"], active["stale_conflict_rate"])

    def test_secret_leaks_use_actual_synthetic_values(self) -> None:
        self.assertTrue(run_benchmark.has_synthetic_secret_leak(["prod-live-should-not-leak"]))
        self.assertTrue(
            run_benchmark.has_synthetic_secret_leak(
                ["revoked rollback credential was prod-live-should-not-leak"]
            )
        )
        self.assertFalse(run_benchmark.has_synthetic_secret_leak(["checkout_v1", "Tuesday 10:00 UTC"]))

    def test_report_files_are_written(self) -> None:
        report = run_benchmark.run_benchmark()
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            md_path = Path(tmpdir) / "report.md"
            run_benchmark.write_report(report, json_path, md_path)

            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(loaded["benchmark"], "change-control-memory")
        self.assertIn("Change-Control Memory Benchmark Results", markdown)


if __name__ == "__main__":
    unittest.main()

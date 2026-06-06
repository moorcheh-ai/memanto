from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("run_benchmark.py")
spec = importlib.util.spec_from_file_location("privacy_consent_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules["privacy_consent_benchmark"] = benchmark
spec.loader.exec_module(benchmark)


class PrivacyConsentBenchmarkTest(unittest.TestCase):
    def test_active_digest_honors_erasure_and_revocation(self) -> None:
        report = benchmark.run()
        summaries = {item["backend"]: item for item in report["summaries"]}

        active = summaries["active_consent_digest"]
        self.assertEqual(active["accuracy"], 1.0)
        self.assertEqual(active["stale_leak_rate"], 0.0)
        self.assertEqual(active["erased_leak_rate"], 0.0)

    def test_append_only_log_leaks_stale_or_erased_memory(self) -> None:
        report = benchmark.run()
        summaries = {item["backend"]: item for item in report["summaries"]}

        append_only = summaries["append_only_log"]
        self.assertLess(append_only["accuracy"], 0.5)
        self.assertGreater(append_only["stale_leak_rate"], 0.0)
        self.assertGreater(append_only["erased_leak_rate"], 0.0)

    def test_recent_window_loses_older_valid_constraints(self) -> None:
        report = benchmark.run()
        summaries = {item["backend"]: item for item in report["summaries"]}

        recent = summaries["recent_window_log"]
        self.assertLess(recent["accuracy"], 1.0)
        self.assertLess(recent["avg_retrieved_tokens"], summaries["append_only_log"]["avg_retrieved_tokens"])


if __name__ == "__main__":
    unittest.main()

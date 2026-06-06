import unittest

import run_benchmark


class SupportEscalationBenchmarkTest(unittest.TestCase):
    """Validate current-fact recall, erased-secret suppression, and baselines."""

    def test_active_digest_keeps_current_facts(self):
        """The active digest should retain every current objective fact."""

        digest = run_benchmark.build_active_digest(run_benchmark.EVENTS)

        self.assertEqual(digest["plan"], "enterprise")
        self.assertEqual(digest["region"], "eu-central")
        self.assertEqual(digest["sla"], "4 hours")
        self.assertEqual(digest["owner"], "Priya")
        self.assertEqual(digest["severity"], "P1")
        self.assertEqual(digest["blocker"], "payroll export")
        self.assertEqual(digest["rollback_window"], "02:00-03:00 UTC")

    def test_erased_secret_is_not_retrieved(self):
        """Erased secret probes should return a refusal instead of old notes."""

        digest = run_benchmark.build_active_digest(run_benchmark.EVENTS)
        probe = next(p for p in run_benchmark.PROBES if p.key == "erased_secret")

        answer = run_benchmark.active_digest_retrieve(digest, probe)

        self.assertEqual(answer, "no erased secret is retrievable")
        self.assertNotIn("beta API key", answer)

    def test_active_digest_beats_baselines(self):
        """The compact digest should outperform append-only retrieval."""

        results = run_benchmark.run()
        by_name = {row["strategy"]: row for row in results["strategies"]}

        self.assertEqual(by_name["active_case_digest"]["accuracy"], 1.0)
        self.assertLess(by_name["active_case_digest"]["stale_leak_rate"], by_name["append_only_log"]["stale_leak_rate"])
        self.assertLess(by_name["active_case_digest"]["avg_retrieved_tokens"], by_name["append_only_log"]["avg_retrieved_tokens"])


if __name__ == "__main__":
    unittest.main()

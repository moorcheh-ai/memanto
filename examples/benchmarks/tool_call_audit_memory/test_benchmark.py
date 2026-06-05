import unittest

from .run_benchmark import ActiveAuditDigest, EVENTS, QUERIES, leaks_secret, run


class ToolCallAuditMemoryBenchmarkTests(unittest.TestCase):
    def test_active_digest_beats_append_only_accuracy(self) -> None:
        report = run()
        results = {item["backend"]: item for item in report["results"]}

        self.assertGreater(
            results["active_audit_digest"]["accuracy"],
            results["append_only_log"]["accuracy"],
        )
        self.assertEqual(results["active_audit_digest"]["secret_leak_rate"], 0)
        self.assertLess(
            results["active_audit_digest"]["avg_retrieved_tokens"],
            results["append_only_log"]["avg_retrieved_tokens"],
        )

    def test_active_digest_suppresses_stale_flag(self) -> None:
        backend = ActiveAuditDigest(EVENTS)
        context = backend.retrieve("Which feature flag should the benchmark docs tell users to set?")

        self.assertIn("MEMANTO_AUDIT_MEMORY", context)
        self.assertNotIn("MEMANTO_USE_MEMORY_V1", context)

    def test_secret_context_is_redacted(self) -> None:
        backend = ActiveAuditDigest(EVENTS)
        context = backend.retrieve("What should be injected about the observed Stripe secret?")

        self.assertIn("<redacted>", context)
        self.assertFalse(leaks_secret(context))

    def test_all_queries_have_expected_answers(self) -> None:
        for query in QUERIES:
            self.assertTrue(query.must_have, query.question)


if __name__ == "__main__":
    unittest.main()

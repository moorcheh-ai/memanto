import unittest

from .run_benchmark import (
    ActiveAuditDigest,
    EVENTS,
    QUERIES,
    evaluate_backend,
    leaks_secret,
    run,
)


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
        backend = ActiveAuditDigest(EVENTS)
        for query in QUERIES:
            context = backend.retrieve(query.question)
            normalized = context.lower()

            for expected in query.must_have:
                self.assertIn(
                    expected.lower(),
                    normalized,
                    f"Expected value {expected!r} not found for query: {query.question}",
                )
            for stale in query.must_not_have:
                self.assertNotIn(
                    stale.lower(),
                    normalized,
                    f"Stale value {stale!r} found for query: {query.question}",
                )

    def test_empty_query_set_returns_zero_metrics(self) -> None:
        backend = ActiveAuditDigest(EVENTS)
        result = evaluate_backend(backend, ())

        self.assertEqual(result["backend"], "active_audit_digest")
        self.assertEqual(result["accuracy"], 0.0)
        self.assertEqual(result["avg_retrieved_tokens"], 0.0)
        self.assertEqual(result["p95_latency_ms"], 0.0)
        self.assertEqual(result["stale_conflict_rate"], 0.0)
        self.assertEqual(result["secret_leak_rate"], 0.0)
        self.assertEqual(result["rows"], [])


if __name__ == "__main__":
    unittest.main()

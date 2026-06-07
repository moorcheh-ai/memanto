import unittest

from run_benchmark import ActiveSecurityDigest, CHECKPOINT_PROBES, DATASET, PROBES, PassiveGraphMemory, run_benchmark


class SecurityReviewEvidenceBenchmarkTests(unittest.TestCase):
    """Regression tests for the security review evidence benchmark."""

    def test_active_digest_redacts_synthetic_secret(self):
        """The active digest should never return the synthetic token value."""
        backend = ActiveSecurityDigest()
        for event in DATASET:
            backend.ingest(event)

        context = backend.retrieve("Should the old GitHub token value be shown?")

        self.assertIn("redacted", context.lower())
        self.assertNotIn("GITHUB_TOKEN_FAKE_FOR_TEST_ONLY", context)
        self.assertIn("raw token values must stay redacted", context)

    def test_active_digest_keeps_latest_finding_status(self):
        """The active digest should preserve only the latest finding state."""
        backend = ActiveSecurityDigest()
        for event in DATASET:
            backend.ingest(event)

        context = backend.retrieve("What is current status of F-102?")

        self.assertIn("F-102 status=resolved", context)
        self.assertIn("zap-42", context)
        self.assertNotIn("F-102 status=open", context)

    def test_passive_graph_keeps_stale_and_sensitive_history(self):
        """The passive graph baseline should expose stale and sensitive facts."""
        backend = PassiveGraphMemory()
        for event in DATASET:
            backend.ingest(event)

        context = backend.retrieve("What is current status of F-102?")

        self.assertIn("F-102 status=open", context)
        self.assertIn("F-102 status=resolved", context)
        self.assertIn("GITHUB_TOKEN_FAKE_FOR_TEST_ONLY", context)

    def test_benchmark_metrics_rank_active_digest(self):
        """The active digest should outrank noisy transcript baselines."""
        result = run_benchmark()
        by_backend = {item["backend"]: item for item in result["results"]}

        active = by_backend["active_security_digest"]
        append_only = by_backend["append_only_log"]
        recent = by_backend["recent_window_log"]

        self.assertGreater(active["accuracy"], append_only["accuracy"])
        self.assertGreater(active["accuracy"], recent["accuracy"])
        self.assertLess(active["avg_retrieved_tokens"], append_only["avg_retrieved_tokens"])
        self.assertEqual(active["cross_session_degradation_rate"], 0.0)
        self.assertEqual(active["secret_leak_rate"], 0.0)
        self.assertGreater(append_only["secret_leak_rate"], 0.0)

    def test_session_accuracy_curve_tracks_each_ingested_session(self):
        """Checkpoint metrics should show whether memory degrades over sessions."""
        result = run_benchmark()
        by_backend = {item["backend"]: item for item in result["results"]}

        active = by_backend["active_security_digest"]
        append_only = by_backend["append_only_log"]

        self.assertEqual(result["checkpoint_count"], len(CHECKPOINT_PROBES))
        self.assertEqual(len(active["session_accuracy_curve"]), len(DATASET))
        self.assertTrue(all(point["accuracy"] == 1.0 for point in active["session_accuracy_curve"]))
        self.assertGreater(append_only["cross_session_degradation_rate"], 0.0)

    def test_probe_results_have_expected_schema(self):
        """Each backend should return a probe result for every probe."""
        result = run_benchmark()

        self.assertEqual(result["probe_count"], len(PROBES))
        for backend_result in result["results"]:
            self.assertEqual(len(backend_result["probe_results"]), len(PROBES))
            self.assertEqual(len(backend_result["checkpoint_results"]), len(CHECKPOINT_PROBES))
            for probe_result in backend_result["probe_results"]:
                self.assertIn("question", probe_result)
                self.assertIn("passed", probe_result)
                self.assertIn("retrieved_tokens", probe_result)


if __name__ == "__main__":
    unittest.main()

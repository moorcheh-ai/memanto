"""Tests for the release-readiness memory benchmark."""

import unittest

from run_benchmark import ActiveReleaseDigest, AppendOnlyLog, iter_events, load_dataset, run


class ReleaseReadinessBenchmarkTest(unittest.TestCase):
    """Regression tests for benchmark scoring and dataset invariants."""

    def test_active_digest_beats_append_only_accuracy(self) -> None:
        """Active digest should outperform the append-only baseline."""

        report = run()
        by_backend = {result["backend"]: result for result in report["results"]}
        self.assertEqual(by_backend["active_release_digest"]["accuracy"], 1.0)
        self.assertLess(
            by_backend["append_only_log"]["accuracy"],
            by_backend["active_release_digest"]["accuracy"],
        )

    def test_active_digest_suppresses_secret_events(self) -> None:
        """Active digest should never return synthetic secret events."""

        events = list(iter_events(load_dataset()))
        digest = ActiveReleaseDigest(events)
        retrieved = digest.retrieve(["secret", "payment_rail"])
        self.assertTrue(retrieved)
        self.assertFalse(any(event.status == "secret" for event in retrieved))

    def test_append_only_exposes_stale_or_secret_context(self) -> None:
        """Append-only baseline should expose stale and secret context."""

        events = list(iter_events(load_dataset()))
        baseline = AppendOnlyLog(events)
        retrieved = baseline.retrieve(["payment_rail", "secret"])
        self.assertTrue(any(event.status == "stale" for event in retrieved))
        self.assertTrue(any(event.status == "secret" for event in retrieved))

    def test_dataset_shape_is_stable(self) -> None:
        """Dataset size should remain stable for reproducible comparisons."""

        dataset = load_dataset()
        self.assertEqual(len(dataset["sessions"]), 4)
        self.assertEqual(len(dataset["queries"]), 7)
        self.assertEqual(len(list(iter_events(dataset))), 12)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from long_horizon.dataset import Probe, canonical_marker
from long_horizon.scoring import (
    RetrievedItem,
    bootstrap_mean_ci,
    parse_markers,
    percentile,
    score_probe,
)


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.probe = Probe(
            probe_id="probe",
            checkpoint=16,
            fact_key="production_region",
            query="Current region?",
            expected_value="eu-west-1",
            stale_values=("us-east-1",),
        )
        self.count_tokens = lambda text: len(text.split())

    def test_current_only_result_is_strictly_correct(self) -> None:
        items = [
            RetrievedItem(
                text=canonical_marker("production_region", "eu-west-1"),
                rank=1,
            )
        ]
        score = score_probe(self.probe, items, self.count_tokens)
        self.assertTrue(score.top1_correct)
        self.assertTrue(score.current_recalled)
        self.assertTrue(score.strict_correct)
        self.assertFalse(score.stale_conflict)
        self.assertEqual(score.current_rank, 1)

    def test_current_and_stale_results_are_not_strictly_correct(self) -> None:
        items = [
            RetrievedItem(
                text=canonical_marker("production_region", "eu-west-1"),
                rank=1,
            ),
            RetrievedItem(
                text=canonical_marker("production_region", "us-east-1"),
                rank=2,
            ),
        ]
        score = score_probe(self.probe, items, self.count_tokens)
        self.assertTrue(score.top1_correct)
        self.assertTrue(score.current_recalled)
        self.assertFalse(score.strict_correct)
        self.assertTrue(score.stale_conflict)

    def test_current_result_below_rank_one_is_not_top1_correct(self) -> None:
        items = [
            RetrievedItem(
                text=canonical_marker("production_region", "us-east-1"),
                rank=1,
            ),
            RetrievedItem(
                text=canonical_marker("production_region", "eu-west-1"),
                rank=2,
            ),
        ]
        score = score_probe(self.probe, items, self.count_tokens)
        self.assertFalse(score.top1_correct)
        self.assertTrue(score.current_recalled)

    def test_marker_parser_does_not_use_substring_matching(self) -> None:
        markers = parse_markers(
            "Values: CANONICAL[production_region=us-east-1] and us-east."
        )
        self.assertEqual(markers, {("production_region", "us-east-1")})

    def test_percentile_interpolates(self) -> None:
        self.assertEqual(percentile([0.0, 10.0], 50), 5.0)
        self.assertEqual(percentile([4.0], 95), 4.0)

    def test_bootstrap_interval_is_deterministic(self) -> None:
        first = bootstrap_mean_ci([0.0, 1.0, 1.0, 1.0], samples=500)
        second = bootstrap_mean_ci([0.0, 1.0, 1.0, 1.0], samples=500)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

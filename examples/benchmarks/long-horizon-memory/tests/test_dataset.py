from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

import long_horizon.dataset as dataset
from long_horizon.dataset import FACTS, canonical_marker, generate_scenario


class DatasetTests(unittest.TestCase):
    """Validate deterministic scenario construction and input bounds."""

    def test_scenario_is_deterministic(self) -> None:
        first = generate_scenario(seed=7, sessions=16, checkpoints=(8, 16))
        second = generate_scenario(seed=7, sessions=16, checkpoints=(8, 16))
        self.assertEqual(first, second)

    def test_each_checkpoint_has_current_state_for_every_fact(self) -> None:
        events, probes = generate_scenario(
            seed=19,
            sessions=24,
            checkpoints=(8, 16, 24),
        )
        self.assertEqual(len(events), 24)
        self.assertEqual(len(probes), len(FACTS) * 3)
        for checkpoint in (8, 16, 24):
            checkpoint_probes = [
                probe for probe in probes if probe.checkpoint == checkpoint
            ]
            self.assertEqual(
                {probe.fact_key for probe in checkpoint_probes},
                {fact.key for fact in FACTS},
            )

    def test_event_contains_machine_readable_ground_truth(self) -> None:
        events, _ = generate_scenario(seed=43, sessions=8, checkpoints=(8,))
        for event in events:
            self.assertIn(
                canonical_marker(event.fact_key, event.value),
                event.content,
            )

    def test_invalid_partial_epoch_checkpoint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "complete eight-session"):
            generate_scenario(seed=7, sessions=16, checkpoints=(9, 16))

    def test_session_limit_uses_shortest_fact_history(self) -> None:
        shortened_facts = (
            replace(FACTS[0], values=FACTS[0].values[:-1]),
            *FACTS[1:],
        )
        with (
            patch.object(dataset, "FACTS", shortened_facts),
            self.assertRaisesRegex(ValueError, "available unique fact versions"),
        ):
            dataset.generate_scenario(seed=7, sessions=41, checkpoints=(8,))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from long_horizon.dataset import FACTS, canonical_marker, generate_scenario


class DatasetTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

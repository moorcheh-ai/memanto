import unittest
from unittest.mock import MagicMock, PropertyMock
from adversarial_memory.scoring import ScoreCalculator
from adversarial_memory.dataset import AdversarialMemoryDataset


class TestContradictionHandling(unittest.TestCase):
    def test_update_overwrite_ignores_timeline(self):
        """Reproduces a bug where the scoring module gives full credit when retrieval
        returns both the outdated and the updated memory, failing to detect a contradiction.
        A correct system must penalize such contradictory states.
        """
        # Simulate a memory adapter that returns both old and new memories unordered
        adapter = MagicMock()
        adapter.retrieve = MagicMock(return_value=[
            {"content": "User's favorite color is blue", "timestamp": 100},
            {"content": "User's favorite color is red",   "timestamp": 200},
        ])

        # Use the real dataset generator to create a query scenario
        dataset = AdversarialMemoryDataset()
        # Dataset might have a method to generate a specific contradiction scenario
        # We assume it returns (query, expected_answer) for a simple preference update
        # This call may fail if the dataset does not expose such a method; adjust as needed.
        # For demonstration, we hardcode the expected latest answer.
        query = "What is the user's favorite color?"
        expected = "red"  # the most recent fact

        # Compute score using the real scoring logic
        calculator = ScoreCalculator()
        score = calculator.compute_score(retrieved=adapter.retrieve(query),
                                         ground_truth=expected)

        # A correct memory system should realize the contradiction and either
        # ask for clarification or return a low confidence score (< 0.5).
        # If the score is high (>0.5), it indicates the system failed to handle the update.
        self.assertLessEqual(
            score, 0.5,
            f"BUG: score={score:.2f} is too high for contradictory memories. "
            "The scoring module does not penalize the coexistence of old and new facts."
        )


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import run_benchmark


class MultiAgentCodeHandoffBenchmarkTests(unittest.TestCase):
    def test_dataset_loads_with_cross_agent_questions(self) -> None:
        _, events, questions = run_benchmark.load_dataset(
            run_benchmark.DEFAULT_DATASET
        )

        self.assertGreaterEqual(len(events), 10)
        self.assertGreaterEqual(len(questions), 8)
        self.assertTrue(
            all(question.requires_cross_agent_memory for question in questions)
        )

    def test_shared_digest_beats_append_only_baseline(self) -> None:
        result = run_benchmark.run(run_benchmark.DEFAULT_DATASET)
        by_backend = {item["backend"]: item for item in result["results"]}
        shared = by_backend["shared_active_digest"]
        shared_log = by_backend["shared_append_log"]
        baseline = by_backend["per_agent_append_log"]

        self.assertGreaterEqual(shared["accuracy"], shared_log["accuracy"])
        self.assertGreater(shared["accuracy"], baseline["accuracy"])
        self.assertLess(shared["retrieved_tokens"], shared_log["retrieved_tokens"])
        self.assertGreater(
            shared["cross_agent_accuracy"], baseline["cross_agent_accuracy"]
        )
        self.assertLess(shared["retrieved_tokens"], baseline["retrieved_tokens"])
        self.assertEqual(shared["stale_conflict_rate"], 0.0)

    def test_reports_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "latest.json"
            markdown = Path(tmpdir) / "latest.md"
            result = run_benchmark.run(run_benchmark.DEFAULT_DATASET)

            output.write_text(json.dumps(result), encoding="utf-8")
            markdown.write_text(
                run_benchmark.markdown_report(result), encoding="utf-8"
            )

            self.assertIn("shared_active_digest", output.read_text())
            self.assertIn("| Backend | Accuracy |", markdown.read_text())


if __name__ == "__main__":
    unittest.main()

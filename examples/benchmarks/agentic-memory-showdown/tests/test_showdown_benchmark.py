"""Regression tests for the agentic memory showdown benchmark example."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_ROOT))

from showdown_benchmark import dataset, runner  # noqa: E402


class ShowdownBenchmarkTest(unittest.TestCase):
    """Verify the benchmark stays reproducible and comparison-oriented."""

    def test_dataset_contains_temporal_preference_conflicts(self) -> None:
        """The fixture should stress-test stale preference handling."""
        scenario = dataset.load_scenario()

        self.assertEqual(scenario.name, "shifting-persona-temporal-tracking")
        self.assertGreaterEqual(len(scenario.sessions), 4)
        self.assertGreaterEqual(len(scenario.questions), 4)
        self.assertTrue(
            any("prefers concise executive briefs" in turn.content for turn in scenario.turns)
        )
        self.assertTrue(
            any("now wants detailed launch-risk memos" in turn.content for turn in scenario.turns)
        )

    def test_runner_outputs_required_metrics_for_both_backends(self) -> None:
        """The benchmark should report the core #639 success-matrix metrics."""
        result = runner.run_benchmark()

        self.assertEqual(
            [backend.name for backend in result.backends],
            ["memanto-active-memory", "graph-style-append-log"],
        )
        for backend in result.backends:
            self.assertGreater(backend.total_tokens_ingested, 0)
            self.assertGreater(backend.total_tokens_retrieved, 0)
            self.assertGreaterEqual(backend.retrieval_accuracy, 0.0)
            self.assertLessEqual(backend.retrieval_accuracy, 1.0)
            self.assertGreaterEqual(backend.p95_latency_seconds, 0.0)

    def test_report_is_machine_and_human_readable(self) -> None:
        """The report should be ready for PR review and social showcase summaries."""
        result = runner.run_benchmark()
        payload = json.loads(result.to_json())
        markdown = result.to_markdown()

        self.assertIn("benchmark", payload)
        self.assertIn("backends", payload)
        self.assertIn("Total Tokens Ingested", markdown)
        self.assertIn("p95 Latency", markdown)
        self.assertIn("Retrieval Accuracy", markdown)
        self.assertIn("Reproducibility Notes", markdown)

    def test_cli_writes_markdown_and_json_outputs(self) -> None:
        """Reviewers should be able to regenerate both report formats from the CLI."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            markdown_path = tmpdir / "report.md"
            json_path = tmpdir / "report.json"

            markdown_run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "showdown_benchmark",
                    "--format",
                    "markdown",
                    "--output",
                    str(markdown_path),
                ],
                cwd=EXAMPLE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            json_run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "showdown_benchmark",
                    "--format",
                    "json",
                    "--output",
                    str(json_path),
                ],
                cwd=EXAMPLE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(markdown_run.returncode, 0, markdown_run.stderr)
            self.assertEqual(json_run.returncode, 0, json_run.stderr)
            self.assertIn("Retrieval Accuracy", markdown_path.read_text())
            self.assertIn("backends", json.loads(json_path.read_text()))

    def test_example_documents_reproducible_submission_artifacts(self) -> None:
        """The bounty folder should include setup, methodology, and sample metrics."""
        readme = EXAMPLE_ROOT / "README.md"
        requirements = EXAMPLE_ROOT / "requirements.txt"
        sample = EXAMPLE_ROOT / "results" / "sample_results.md"

        self.assertTrue(readme.exists())
        self.assertTrue(requirements.exists())
        self.assertTrue(sample.exists())

        readme_text = readme.read_text(encoding="utf-8")
        sample_text = sample.read_text(encoding="utf-8")

        self.assertIn("MOORCHEH_API_KEY", readme_text)
        self.assertIn("MEM0_API_KEY", readme_text)
        self.assertIn("July 1st, 2026", readme_text)
        self.assertIn("p95 Latency", sample_text)
        self.assertIn("Retrieval Accuracy", sample_text)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from run_benchmark import (
    build_dataset,
    evaluate_backend,
    main,
)


class ComplianceEvidenceBenchmarkTest(unittest.TestCase):
    def test_active_digest_preserves_current_evidence_with_lower_footprint(self):
        dataset = build_dataset()

        active = evaluate_backend("active_evidence_digest", dataset)
        append_only = evaluate_backend("append_only_log", dataset)
        recent_window = evaluate_backend("recent_window_log", dataset)

        self.assertEqual(active.accuracy, 1.0)
        self.assertEqual(active.stale_conflict_rate, 0.0)
        self.assertEqual(active.missing_evidence_rate, 0.0)
        self.assertLess(active.avg_retrieved_tokens, append_only.avg_retrieved_tokens)
        self.assertGreater(active.accuracy, recent_window.accuracy)

    def test_cli_writes_reproducible_json_and_markdown_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "results.json"
            markdown_path = Path(tmp) / "results.md"

            exit_code = main(
                [
                    "--output",
                    str(json_path),
                    "--markdown",
                    str(markdown_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["benchmark"], "compliance-evidence-memory")
            self.assertEqual(len(payload["results"]), 3)
            self.assertIn("active_evidence_digest", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

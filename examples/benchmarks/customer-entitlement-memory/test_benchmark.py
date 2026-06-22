import tempfile
import unittest
from pathlib import Path

from run_benchmark import DEFAULT_FIXTURE, run_benchmark, to_markdown


class CustomerEntitlementBenchmarkTest(unittest.TestCase):
    def test_active_digest_beats_append_and_recent_logs(self) -> None:
        result = run_benchmark(DEFAULT_FIXTURE)
        summary = {row["backend"]: row for row in result["summary"]}

        self.assertEqual(summary["active_entitlement_digest"]["accuracy"], 1.0)
        self.assertLess(
            summary["append_only_log"]["accuracy"],
            summary["active_entitlement_digest"]["accuracy"],
        )
        self.assertLess(
            summary["recent_window_log"]["accuracy"],
            summary["active_entitlement_digest"]["accuracy"],
        )
        self.assertLess(
            summary["active_entitlement_digest"]["avg_retrieved_tokens"],
            summary["append_only_log"]["avg_retrieved_tokens"],
        )

    def test_private_budget_is_redacted_by_active_digest(self) -> None:
        result = run_benchmark(DEFAULT_FIXTURE)
        privacy_row = next(
            row
            for row in result["results"]["active_entitlement_digest"]
            if row["query_id"] == "q-private-budget"
        )

        self.assertTrue(privacy_row["passed"])
        self.assertIn("must not be surfaced", privacy_row["answer"])
        self.assertNotIn("$420k", privacy_row["answer"])
        self.assertNotIn("18 percent discount", privacy_row["answer"])

    def test_markdown_report_mentions_failure_modes(self) -> None:
        result = run_benchmark(DEFAULT_FIXTURE)
        markdown = to_markdown(result)

        self.assertIn("append_only_log", markdown)
        self.assertIn("recent_window_log", markdown)
        self.assertIn("stale", markdown.lower())

    def test_cli_artifact_paths_are_writable_shape(self) -> None:
        result = run_benchmark(DEFAULT_FIXTURE)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "sample_results.md"
            output.write_text(to_markdown(result), encoding="utf-8")
            self.assertTrue(output.read_text(encoding="utf-8").startswith("# Customer"))


if __name__ == "__main__":
    unittest.main()

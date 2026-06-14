import tempfile
import unittest
import json
from pathlib import Path

import run_benchmark


class ResearchDecisionMemoryBenchmarkTest(unittest.TestCase):
    def test_active_digest_keeps_current_decisions(self) -> None:
        payload = run_benchmark.run()
        summary = self._summary(payload, "active_decision_digest")

        self.assertEqual(summary["accuracy"], 1.0)
        self.assertEqual(summary["evidence_coverage"], 1.0)
        self.assertEqual(summary["stale_conflict_rate"], 0.0)
        self.assertEqual(summary["secret_leak_rate"], 0.0)

    def test_append_only_log_retrieves_stale_context(self) -> None:
        payload = run_benchmark.run()
        active = self._summary(payload, "active_decision_digest")
        append_only = self._summary(payload, "append_only_log")

        self.assertGreater(
            append_only["avg_retrieved_tokens"], active["avg_retrieved_tokens"]
        )
        self.assertGreater(append_only["stale_conflict_rate"], 0.0)
        self.assertLess(append_only["accuracy"], active["accuracy"])

    def test_recent_window_forgets_older_current_decisions(self) -> None:
        payload = run_benchmark.run()
        recent = self._summary(payload, "recent_window_log")

        self.assertLess(recent["accuracy"], 1.0)
        target_answer = self._answer(payload, "recent_window_log", "target_segment")
        self.assertEqual(target_answer["answer"], "No decision found.")

    def test_passive_graph_history_keeps_conflicting_states(self) -> None:
        payload = run_benchmark.run()
        graph = self._summary(payload, "passive_graph_history")

        self.assertGreater(graph["stale_conflict_rate"], 0.0)
        self.assertLess(graph["accuracy"], 1.0)

    def test_writers_emit_reproducible_json_and_markdown(self) -> None:
        payload = run_benchmark.run()
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "results.json"
            md_path = Path(tmpdir) / "results.md"
            run_benchmark.write_json(json_path, payload)
            run_benchmark.write_markdown(md_path, payload)

            json_text = json_path.read_text()
            markdown_text = md_path.read_text()
            self.assertIn("active_decision_digest", json_text)
            self.assertNotIn("p95_latency_ms", json_text)
            self.assertNotIn("latency_ms", json_text)
            self.assertIn("Research Decision Memory Results", markdown_text)
            self.assertNotIn("| p95 ms |", markdown_text)

            sample_dir = Path(__file__).parent / "results"
            self.assertEqual(
                json.loads(json_text),
                json.loads((sample_dir / "sample_results.json").read_text()),
            )
            self.assertEqual(
                markdown_text,
                (sample_dir / "sample_results.md").read_text(),
            )

    def test_live_markdown_keeps_latency_metric(self) -> None:
        payload = run_benchmark.run()

        report = run_benchmark.markdown_report(payload)

        self.assertIn("p95 ms", report)

    @staticmethod
    def _summary(payload: dict, backend: str) -> dict:
        for summary in payload["summaries"]:
            if summary["backend"] == backend:
                return summary
        raise AssertionError(f"Missing summary for {backend}")

    @staticmethod
    def _answer(payload: dict, backend: str, probe: str) -> dict:
        for answer in payload["answers"][backend]:
            if answer["probe"] == probe:
                return answer
        raise AssertionError(f"Missing answer for {backend}:{probe}")


if __name__ == "__main__":
    unittest.main()

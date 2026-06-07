"""Unit tests for the fabric-entertainment-curator benchmark.

Run with:
    python -m unittest discover -s . -p test_*.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Ensure package-local imports resolve.
sys.path.insert(0, str(Path(__file__).parent))


class TestActiveDigestBackend(unittest.TestCase):
    """Tests for the Memanto active-digest simulation."""

    def setUp(self) -> None:
        from backends.active_digest import ActiveDigestBackend
        self.backend = ActiveDigestBackend()

    def test_basic_remember_recall(self) -> None:
        self.backend.remember("user1", "Alex loves documentaries.", "preference")
        memories, token_count = self.backend.recall("user1", "what does Alex like?")
        self.assertGreater(len(memories), 0)
        self.assertGreater(token_count, 0)
        self.assertIn("documentaries", " ".join(memories).lower())

    def test_supersedes_contradicted_preference(self) -> None:
        """Adding a contradicting preference should supersede the old one."""
        self.backend.remember("user1", "Alex loves science fiction films.", "preference")
        self.assertEqual(self.backend.active_count, 1)
        self.assertEqual(self.backend.superseded_count, 0)

        # Transition signal: "done with sci-fi blockbusters".
        self.backend.remember(
            "user1",
            "Alex is done with sci-fi blockbusters for now.",
            "preference",
        )
        # Old sci-fi entry should be superseded.
        self.assertEqual(self.backend.active_count, 1)
        self.assertEqual(self.backend.superseded_count, 1)

    def test_does_not_supersede_unrelated(self) -> None:
        """Unrelated memory types/topics should not trigger supersession."""
        self.backend.remember("u", "Alex loves documentaries about history.", "preference")
        self.backend.remember("u", "Alex prefers streaming over theatrical.", "preference")
        # No overlap between documentary and format — both active.
        self.assertGreaterEqual(self.backend.active_count, 2)

    def test_reset_clears_state(self) -> None:
        self.backend.remember("u", "Alex loves sci-fi.", "preference")
        self.backend.reset()
        memories, token_count = self.backend.recall("u", "what does Alex like?")
        self.assertEqual(len(memories), 0)
        self.assertEqual(token_count, 0)
        self.assertEqual(self.backend.active_count, 0)

    def test_token_count_matches_content(self) -> None:
        self.backend.remember("u", "Alex loves K-drama.", "preference")
        memories, token_count = self.backend.recall("u", "recommendations")
        self.assertGreater(token_count, 0)
        self.assertEqual(len(memories), 1)

    def test_horror_ban_superseded_by_updated_stance(self) -> None:
        """Session 2 horror ban should be superseded by session 12 update."""
        self.backend.remember(
            "u", "Alex has a strict no-horror rule and refuses to watch horror.", "preference"
        )
        self.assertEqual(self.backend.active_count, 1)
        self.backend.remember(
            "u",
            "Alex updated their stance: Korean psychological horror is acceptable now.",
            "preference",
        )
        self.assertEqual(self.backend.superseded_count, 1)


class TestAppendOnlyBackend(unittest.TestCase):
    """Tests for the append-only naive baseline."""

    def setUp(self) -> None:
        from backends.append_only import AppendOnlyBackend
        self.backend = AppendOnlyBackend()

    def test_stores_and_recalls_all(self) -> None:
        self.backend.remember("u", "Memory A.", "preference")
        self.backend.remember("u", "Memory B.", "preference")
        memories, _ = self.backend.recall("u", "anything")
        self.assertEqual(len(memories), 2)

    def test_stale_facts_remain(self) -> None:
        """Append-only must NOT remove stale entries — that is the baseline flaw."""
        self.backend.remember("u", "Alex loves science fiction.", "preference")
        self.backend.remember("u", "Alex is done with sci-fi blockbusters.", "preference")
        memories, _ = self.backend.recall("u", "what does Alex like?")
        combined = " ".join(memories).lower()
        self.assertIn("science fiction", combined, "stale entry must still be present")
        self.assertIn("done with sci-fi", combined, "new entry must also be present")

    def test_token_count_grows_with_history(self) -> None:
        _, t1 = self.backend.recall("u", "q")
        self.backend.remember("u", "New memory added.", "preference")
        _, t2 = self.backend.recall("u", "q")
        self.assertGreater(t2, t1)

    def test_reset(self) -> None:
        self.backend.remember("u", "X", "preference")
        self.backend.reset()
        memories, tokens = self.backend.recall("u", "q")
        self.assertEqual(memories, [])
        self.assertEqual(tokens, 0)


class TestKeywordJudge(unittest.TestCase):
    """Tests for the offline keyword accuracy judge."""

    def setUp(self) -> None:
        from judge.accuracy import _keyword_judge  # noqa: PLC0415
        self._judge = _keyword_judge

    def test_perfect_match(self) -> None:
        score = self._judge(
            ["Alex loves documentaries about history and science."],
            "documentaries history science",
        )
        self.assertAlmostEqual(score, 1.0, places=1)

    def test_no_match(self) -> None:
        score = self._judge(["Alex loves sci-fi films."], "documentaries history")
        self.assertLess(score, 0.5)

    def test_empty_retrieved(self) -> None:
        self.assertEqual(self._judge([], "anything"), 0.0)

    def test_partial_match(self) -> None:
        score = self._judge(
            ["Alex enjoys documentaries."],
            "documentaries history science k-drama",
        )
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)


class TestDataset(unittest.TestCase):
    """Validates the dataset file structure."""

    def setUp(self) -> None:
        dataset_path = Path(__file__).parent / "dataset" / "entertainment_sessions.json"
        self.data = json.loads(dataset_path.read_text())

    def test_has_20_sessions(self) -> None:
        self.assertEqual(len(self.data["sessions"]), 20)

    def test_sessions_have_required_fields(self) -> None:
        required = {"session_id", "user_id", "phase", "messages", "query", "ground_truth", "stale_facts"}
        for s in self.data["sessions"]:
            missing = required - set(s.keys())
            self.assertEqual(missing, set(), f"Session {s.get('session_id')} missing: {missing}")

    def test_phase_4_has_stale_facts(self) -> None:
        """Sessions in the documentary phase should declare stale sci-fi facts."""
        phase_4 = [s for s in self.data["sessions"] if s["phase"] == "documentary"]
        self.assertTrue(any(len(s["stale_facts"]) > 0 for s in phase_4))

    def test_all_messages_have_type(self) -> None:
        for s in self.data["sessions"]:
            for msg in s["messages"]:
                self.assertIn("type", msg, f"Message in session {s['session_id']} missing 'type'")


class TestBenchmarkIntegration(unittest.TestCase):
    """Smoke test: runs the full benchmark on first 5 sessions."""

    def test_full_pipeline_smoke(self) -> None:
        from run_benchmark import main  # noqa: PLC0415
        report = main(sessions_limit=5)
        self.assertIn("results", report)
        # All three backends should produce results.
        self.assertEqual(len(report["results"]), 3)
        for name, metrics in report["results"].items():
            with self.subTest(backend=name):
                self.assertIn("avg_retrieved_tokens", metrics)
                self.assertIn("p95_latency_ms", metrics)
                self.assertIn("accuracy", metrics)
                self.assertIn("stale_rate", metrics)
                self.assertGreaterEqual(metrics["avg_retrieved_tokens"], 0)
                self.assertGreaterEqual(metrics["p95_latency_ms"], 0)

    def test_active_digest_fewer_tokens_than_append_only(self) -> None:
        """After accumulating history, active-digest should use fewer tokens."""
        from run_benchmark import main  # noqa: PLC0415
        report = main(sessions_limit=20)
        results = report["results"]
        digest_tokens = results.get("memanto_active_digest", {}).get("avg_retrieved_tokens", 0)
        append_tokens = results.get("append_only_baseline", {}).get("avg_retrieved_tokens", 0)
        if append_tokens > 0:
            self.assertLess(
                digest_tokens,
                append_tokens,
                "Active digest must inject fewer tokens than append-only baseline.",
            )


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the benchmark harness — no API keys required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.base import BackendStats, count_tokens
from dataset import QUERIES, SESSIONS, USER_ID
from run_benchmark import MockBackend, generate_markdown, score_answer


class TestScoring(unittest.TestCase):
    def test_correct_keyword_wins(self):
        correct, stale = score_answer("user prefers python fastapi", ["python"], ["go"])
        self.assertTrue(correct)
        self.assertFalse(stale)

    def test_stale_keyword_detected(self):
        correct, stale = score_answer("user prefers go for backend", ["python"], ["go"])
        self.assertFalse(correct)
        self.assertTrue(stale)

    def test_correct_overrides_stale(self):
        # If answer contains both (transition sentence), correct wins
        correct, stale = score_answer("switched from go to python", ["python"], ["go"])
        self.assertTrue(correct)
        self.assertFalse(stale)

    def test_miss_when_neither(self):
        correct, stale = score_answer("user is happy", ["python"], ["go"])
        self.assertFalse(correct)
        self.assertFalse(stale)


class TestBackendStats(unittest.TestCase):
    def test_p95_single_value(self):
        s = BackendStats()
        s.record_ingest(100, 50.0)
        self.assertEqual(s.ingest_p95_ms, 50.0)

    def test_p95_empty(self):
        s = BackendStats()
        self.assertEqual(s.ingest_p95_ms, 0.0)

    def test_p95_multiple(self):
        s = BackendStats()
        for ms in [10, 20, 30, 40, 100]:
            s.record_retrieve(10, float(ms))
        # p95 of [10,20,30,40,100] → idx = int(5*0.95)-1 = 3 → 40
        self.assertEqual(s.retrieve_p95_ms, 40.0)

    def test_token_accumulation(self):
        s = BackendStats()
        s.record_ingest(100, 10.0)
        s.record_ingest(200, 20.0)
        self.assertEqual(s.tokens_ingested, 300)


class TestDataset(unittest.TestCase):
    def test_sessions_have_messages(self):
        for session in SESSIONS:
            self.assertIn("messages", session)
            self.assertGreater(len(session["messages"]), 0)

    def test_queries_have_golden_answers(self):
        for q in QUERIES:
            self.assertTrue(q["correct_keywords"])
            self.assertTrue(q["stale_keywords"])

    def test_stale_and_correct_are_disjoint(self):
        for q in QUERIES:
            overlap = set(q["correct_keywords"]) & set(q["stale_keywords"])
            self.assertEqual(overlap, set(), f"Query {q['id']} has overlapping keywords")


class TestMockBackend(unittest.TestCase):
    def test_mock_ingest_records_stats(self):
        backend = MockBackend("test")
        backend.add([{"role": "user", "content": "hello world"}], "user1")
        self.assertGreater(backend.stats.tokens_ingested, 0)

    def test_mock_search_returns_string(self):
        backend = MockBackend("test")
        result = backend.search("what language?", "user1")
        self.assertIsInstance(result, str)


class TestReportGeneration(unittest.TestCase):
    def test_markdown_contains_table(self):
        mock_results = {
            "Backend A": {
                "accuracy_pct": 83.3,
                "stale_rate_pct": 0.0,
                "tokens_ingested": 500,
                "tokens_retrieved": 100,
                "ingest_p95_ms": 120.0,
                "retrieve_p95_ms": 35.0,
                "queries": [
                    {"query_id": "q1", "query": "test?", "retrieved": "python",
                     "correct": True, "stale": False, "explanation": "test"},
                ],
            },
            "Backend B": {
                "accuracy_pct": 50.0,
                "stale_rate_pct": 33.3,
                "tokens_ingested": 1200,
                "tokens_retrieved": 450,
                "ingest_p95_ms": 890.0,
                "retrieve_p95_ms": 210.0,
                "queries": [
                    {"query_id": "q1", "query": "test?", "retrieved": "go",
                     "correct": False, "stale": True, "explanation": "test"},
                ],
            },
        }
        md = generate_markdown(mock_results)
        self.assertIn("Summary Table", md)
        self.assertIn("Accuracy", md)
        self.assertIn("Backend A", md)
        self.assertIn("Backend B", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)

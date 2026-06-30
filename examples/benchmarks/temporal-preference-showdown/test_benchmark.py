"""Unit tests for the benchmark harness — no API keys required."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.base import BackendStats, count_tokens
from dataset import QUERIES, SESSIONS, USER_ID
from run_benchmark import MockBackend, generate_markdown, score_answer


class TestScoring(unittest.TestCase):
    """Tests for the keyword-based answer scoring function."""

    def test_correct_keyword_wins(self):
        """Answer containing only a correct keyword scores as correct."""
        correct, stale = score_answer("user prefers python fastapi", ["python"], ["go"])
        self.assertTrue(correct)
        self.assertFalse(stale)

    def test_stale_keyword_detected(self):
        """Answer containing only a stale keyword scores as stale."""
        correct, stale = score_answer("user prefers go for backend", ["python"], ["go"])
        self.assertFalse(correct)
        self.assertTrue(stale)

    def test_correct_overrides_stale(self):
        """When both correct and stale keywords appear, correct wins (transition sentence)."""
        correct, stale = score_answer("switched from go to python", ["python"], ["go"])
        self.assertTrue(correct)
        self.assertFalse(stale)

    def test_miss_when_neither(self):
        """Answer with no matching keywords is a miss (both False)."""
        correct, stale = score_answer("user is happy", ["python"], ["go"])
        self.assertFalse(correct)
        self.assertFalse(stale)


class TestBackendStats(unittest.TestCase):
    """Tests for stats accumulation and p95 latency calculation."""

    def test_p95_single_value(self):
        """A single-element sample returns that value as p95."""
        s = BackendStats()
        s.record_ingest(100, 50.0)
        self.assertEqual(s.ingest_p95_ms, 50.0)

    def test_p95_empty(self):
        """An empty latency list returns 0.0."""
        s = BackendStats()
        self.assertEqual(s.ingest_p95_ms, 0.0)

    def test_p95_multiple(self):
        """p95 uses linear interpolation: [10,20,30,40,100] → rank=3.8 → 88.0 ms."""
        s = BackendStats()
        for ms in [10, 20, 30, 40, 100]:
            s.record_retrieve(10, float(ms))
        # rank = (5-1)*0.95 = 3.8 → 40 + 0.8*(100-40) = 88.0
        self.assertEqual(s.retrieve_p95_ms, 88.0)

    def test_token_accumulation(self):
        """Tokens from multiple ingest calls accumulate correctly."""
        s = BackendStats()
        s.record_ingest(100, 10.0)
        s.record_ingest(200, 20.0)
        self.assertEqual(s.tokens_ingested, 300)


class TestCountTokens(unittest.TestCase):
    """Tests for the approximate token counting utility."""

    def test_empty_string_returns_zero(self):
        """Empty input must return 0 (not 1)."""
        self.assertEqual(count_tokens(""), 0)

    def test_whitespace_only_returns_zero(self):
        """Whitespace-only input must return 0."""
        self.assertEqual(count_tokens("   "), 0)

    def test_nonempty_approximation(self):
        """Non-empty text returns a positive token estimate."""
        self.assertGreater(count_tokens("hello world"), 0)


class TestDataset(unittest.TestCase):
    """Tests for dataset integrity — no API calls needed."""

    def test_sessions_have_messages(self):
        """Every session must contain at least one message."""
        for session in SESSIONS:
            self.assertIn("messages", session)
            self.assertGreater(len(session["messages"]), 0)

    def test_queries_have_golden_answers(self):
        """Every query must have non-empty correct and stale keyword lists."""
        for q in QUERIES:
            self.assertTrue(q["correct_keywords"])
            self.assertTrue(q["stale_keywords"])

    def test_stale_and_correct_are_disjoint(self):
        """Correct and stale keyword sets must not overlap within any query."""
        for q in QUERIES:
            overlap = set(q["correct_keywords"]) & set(q["stale_keywords"])
            self.assertEqual(overlap, set(), f"Query {q['id']} has overlapping keywords")


class TestMockBackend(unittest.TestCase):
    """Tests for the dry-run mock backend."""

    def test_mock_ingest_records_stats(self):
        """Ingesting messages must record a positive token count."""
        backend = MockBackend("test")
        backend.add([{"role": "user", "content": "hello world"}], "user1")
        self.assertGreater(backend.stats.tokens_ingested, 0)

    def test_mock_search_returns_string(self):
        """Search must always return a non-None string."""
        backend = MockBackend("test")
        result = backend.search("what language?", "user1")
        self.assertIsInstance(result, str)

    def test_mock_correct_rate_respected(self):
        """With correct_rate=1.0 every search must return the correct answer."""
        backend = MockBackend("always-correct", correct_rate=1.0)
        for _ in range(10):
            result = backend.search("query", "user1")
            self.assertIn("python", result)

    def test_mock_zero_correct_rate(self):
        """With correct_rate=0.0 every search must return the stale answer."""
        backend = MockBackend("always-stale", correct_rate=0.0)
        for _ in range(10):
            result = backend.search("query", "user1")
            self.assertIn("go", result)


class TestReportGeneration(unittest.TestCase):
    """Tests for Markdown report generation."""

    def _mock_results(self):
        """Return a minimal two-backend result dict for report tests."""
        return {
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

    def test_markdown_contains_table(self):
        """Generated Markdown must include a summary table with all backend names."""
        md = generate_markdown(self._mock_results())
        self.assertIn("Summary Table", md)
        self.assertIn("Accuracy", md)
        self.assertIn("Backend A", md)
        self.assertIn("Backend B", md)

    def test_markdown_contains_methodology(self):
        """Generated Markdown must include the Methodology section."""
        md = generate_markdown(self._mock_results())
        self.assertIn("Methodology", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)

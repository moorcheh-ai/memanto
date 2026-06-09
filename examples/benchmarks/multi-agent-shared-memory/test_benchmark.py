#!/usr/bin/env python3
"""Tests for the Multi-Agent Shared Memory Benchmark."""

import unittest
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from run_benchmark import (
    RawContextBaseline,
    MockMemanto,
    MockMem0,
    run_benchmark,
    score_answer,
    SESSIONS,
    PROBES,
)


class TestScoring(unittest.TestCase):
    def test_exact_keyword_match(self):
        score = score_answer("I prefer Python", "Python", ["python"])
        self.assertEqual(score, 1.0)

    def test_partial_keyword_match(self):
        score = score_answer("I use Python and pytest", "pytest", ["python", "pytest"])
        self.assertEqual(score, 1.0)

    def test_no_keyword_match(self):
        score = score_answer("I prefer JavaScript", "Python", ["python"])
        self.assertEqual(score, 0.0)

    def test_empty_answer(self):
        score = score_answer("", "Python", ["python"])
        self.assertEqual(score, 0.0)

    def test_case_insensitive(self):
        score = score_answer("PYTHON is great", "Python", ["python"])
        self.assertEqual(score, 1.0)


class TestBackends(unittest.TestCase):
    def test_raw_context_baseline_write(self):
        backend = RawContextBaseline()
        result = backend.write(1, "coder", "Test content")
        self.assertGreater(result.tokens_used, 0)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertEqual(len(backend.history), 1)

    def test_raw_context_baseline_read(self):
        backend = RawContextBaseline()
        backend.write(1, "coder", "Test content")
        result = backend.read("coder", "What?")
        self.assertGreater(result.tokens_used, 0)

    def test_mock_memanto_write(self):
        backend = MockMemanto()
        result = backend.write(1, "coder", "I prefer Python")
        self.assertGreater(result.tokens_used, 0)
        self.assertIn("coder", backend.compressed_state)

    def test_mock_memanto_read(self):
        backend = MockMemanto()
        backend.write(1, "coder", "I prefer Python")
        result = backend.read("coder", "What language?")
        self.assertGreater(result.tokens_used, 0)
        self.assertIn("python", result.text.lower())

    def test_mock_mem0_write(self):
        backend = MockMem0()
        result = backend.write(1, "coder", "I prefer Python")
        self.assertGreater(result.tokens_used, 0)
        self.assertEqual(len(backend.facts), 1)

    def test_mock_mem0_read(self):
        backend = MockMem0()
        backend.write(1, "coder", "I prefer Python")
        result = backend.read("coder", "What language?")
        self.assertIn("python", result.text.lower())

    def test_consistency_check(self):
        backend = MockMemanto()
        backend.write(1, "coder", "Python")
        backend.write(2, "researcher", "AI research")
        consistency = backend.consistency_check(["coder", "researcher"], "What?")
        self.assertGreaterEqual(consistency, 0.0)
        self.assertLessEqual(consistency, 1.0)


class TestBenchmark(unittest.TestCase):
    def test_run_benchmark_raw(self):
        backend = RawContextBaseline()
        result = run_benchmark(backend)
        self.assertEqual(result.name, "raw_context_baseline")
        self.assertGreater(result.total_tokens_written, 0)
        self.assertGreater(result.total_tokens_read, 0)
        self.assertEqual(len(result.probe_results), len(PROBES))

    def test_run_benchmark_memanto(self):
        backend = MockMemanto()
        result = run_benchmark(backend)
        self.assertEqual(result.name, "memanto")
        self.assertGreater(result.total_tokens_written, 0)

    def test_run_benchmark_mem0(self):
        backend = MockMem0()
        result = run_benchmark(backend)
        self.assertEqual(result.name, "mem0")
        self.assertGreater(result.total_tokens_written, 0)

    def test_memanto_uses_fewer_tokens(self):
        """Memanto (compressed) should use fewer write tokens than raw baseline."""
        raw = run_benchmark(RawContextBaseline())
        memanto = run_benchmark(MockMemanto())
        self.assertLessEqual(memanto.total_tokens_written, raw.total_tokens_written)

    def test_all_probes_have_results(self):
        backend = MockMemanto()
        result = run_benchmark(backend)
        self.assertEqual(len(result.probe_results), len(PROBES))
        for pr in result.probe_results:
            self.assertGreaterEqual(pr.accuracy, 0.0)
            self.assertLessEqual(pr.accuracy, 1.0)


class TestDataset(unittest.TestCase):
    def test_sessions_not_empty(self):
        self.assertGreater(len(SESSIONS), 0)

    def test_probes_not_empty(self):
        self.assertGreater(len(PROBES), 0)

    def test_all_agents_covered(self):
        agents = set(s["agent"] for s in SESSIONS)
        self.assertEqual(agents, {"coder", "researcher", "writer"})

    def test_sessions_have_required_fields(self):
        for s in SESSIONS:
            self.assertIn("session_id", s)
            self.assertIn("agent", s)
            self.assertIn("content", s)

    def test_probes_have_required_fields(self):
        for p in PROBES:
            self.assertIn("probe_id", p)
            self.assertIn("agent", p)
            self.assertIn("question", p)
            self.assertIn("expected", p)
            self.assertIn("keywords", p)


if __name__ == "__main__":
    unittest.main()

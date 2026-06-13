"""Tests for the benchmark adapter interfaces and evaluator."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.base import MemoryAdapter, MemoryResult, BenchmarkMetric
from benchmarks.evaluator import LLMEvaluator


# -- MemoryResult tests --

class TestMemoryResult:
    """Tests for the MemoryResult dataclass."""

    def test_success_result(self):
        """Test that a successful MemoryResult stores fields correctly."""
        r = MemoryResult(success=True, latency_ms=42.5, tokens_used=100, data="ok")
        assert r.success is True
        assert r.latency_ms == 42.5
        assert r.tokens_used == 100

    def test_failure_result(self):
        """Test that a failed MemoryResult stores the error message."""
        r = MemoryResult(success=False, latency_ms=0, error="connection refused")
        assert r.success is False
        assert r.error == "connection refused"


# -- BenchmarkMetric tests --

class TestBenchmarkMetric:
    """Tests for the BenchmarkMetric dataclass."""

    def test_empty_metric(self):
        """Test that a new BenchmarkMetric has zero defaults."""
        m = BenchmarkMetric(framework="Test", scenario="S1")
        assert m.store_p95_latency == 0.0
        assert m.retrieve_p95_latency == 0.0
        assert m.mean_retrieval_accuracy == 0.0

    def test_p95_latency(self):
        """Test p95 latency calculation from a list of latencies."""
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.store_latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        assert m.store_p95_latency == 100.0  # 95th percentile of 10 items

    def test_mean_accuracy(self):
        """Test mean retrieval accuracy calculation."""
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.retrieval_scores = [0.8, 0.9, 0.7]
        assert abs(m.mean_retrieval_accuracy - 0.8) < 0.01

    def test_to_dict(self):
        """Test conversion of BenchmarkMetric to a dictionary."""
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.store_latencies = [10, 20]
        d = m.to_dict()
        assert d["framework"] == "Test"
        assert d["scenario"] == "S1"
        assert "store_p95_latency_ms" in d
        assert "retrieval_accuracy" in d


# -- LLMEvaluator tests --

class TestLLMEvaluator:
    """Tests for the LLMEvaluator scoring logic."""

    def test_keyword_score_perfect_match(self):
        """Test keyword scoring returns 1.0 for full overlap."""
        score, reasoning = LLMEvaluator._keyword_score(
            "the cat sat on the mat",
            ["the cat sat on the mat and looked around"],
        )
        assert score == 1.0
        assert "overlap" in reasoning.lower()

    def test_keyword_score_partial_match(self):
        """Test keyword scoring returns a value between 0 and 1 for partial overlap."""
        score, reasoning = LLMEvaluator._keyword_score(
            "the quick brown fox jumps over the lazy dog",
            ["the fox jumped over a dog"],
        )
        assert 0.0 < score < 1.0

    def test_keyword_score_no_match(self):
        """Test keyword scoring returns 0.0 when there is no overlap."""
        score, reasoning = LLMEvaluator._keyword_score(
            "machine learning neural network",
            ["pizza pasta carbonara recipe"],
        )
        assert score == 0.0

    def test_keyword_score_empty_golden(self):
        """Test keyword scoring returns 0.0 for an empty golden answer."""
        score, _ = LLMEvaluator._keyword_score("", ["some text"])
        assert score == 0.0

    def test_evaluator_without_api_key(self, monkeypatch):
        """Test that the evaluator falls back to keyword scoring without an API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        evaluator = LLMEvaluator()
        assert evaluator.client is None
        # Should fall back to keyword scoring
        score, _ = evaluator.score_retrieval(
            "test query", "test answer", ["test answer is here"]
        )
        assert score > 0


# -- Integration: dry-run scenario A --

class TestDryRunScenarioA:
    """Integration tests for Scenario A in dry-run mode."""

    def test_dry_run_loads_dataset(self):
        """Test that the Scenario A dataset loads with expected structure."""
        from benchmarks.scenario_a import load_dataset
        dataset = load_dataset()
        assert len(dataset) == 10
        assert "content" in dataset[0]
        assert "retrieval_queries" in dataset[0]

    def test_dry_run_scenario_a(self):
        """Run Scenario A in dry-run mode with a mock adapter."""
        class MockAdapter(MemoryAdapter):
            """Mock adapter that returns canned responses for testing."""

            @property
            def name(self):
                """Return the mock adapter name."""
                return "Mock"

            def setup(self, uid):
                """No-op setup for the mock adapter."""

            def store(self, content, metadata=None):
                """Return a successful store result with fake latency."""

                return MemoryResult(True, 5.0, len(content.split())*2)

            def retrieve(self, query, limit=5):
                """Return a successful retrieve result with a mock memory."""

                return MemoryResult(True, 3.0, 100, ["mock memory"])

            def update(self, mid, content):
                """Return a successful update result."""

                return MemoryResult(True, 5.0)

            def delete(self, mid):
                """Return a successful delete result."""

                return MemoryResult(True, 2.0)

            def get_all(self):
                """Return an empty list of memories."""

                return MemoryResult(True, 1.0, data=[])

            def cleanup(self):
                """No-op cleanup for the mock adapter."""

        from benchmarks.scenario_a import run_scenario_a
        from benchmarks.evaluator import LLMEvaluator
        import os
        monkeypatch_env = {"OPENAI_API_KEY": ""}
        evaluator = LLMEvaluator(api_key="")
        adapter = MockAdapter()
        metrics = run_scenario_a(adapter, evaluator, dry_run=True)
        assert metrics.total_store_calls == 10
        assert metrics.total_retrieve_calls > 0
        assert metrics.store_p95_latency > 0


# -- Integration: dry-run scenario B --

class TestDryRunScenarioB:
    """Integration tests for Scenario B in dry-run mode."""

    def test_dry_run_loads_dataset(self):
        """Test that the Scenario B dataset loads with expected structure."""
        from benchmarks.scenario_b import load_dataset
        dataset = load_dataset()
        assert len(dataset) == 4
        assert "session_id" in dataset[0]
        assert "evaluation_queries" in dataset[0]

    def test_dry_run_scenario_b(self):
        """Run Scenario B in dry-run mode with a mock adapter."""
        from benchmarks.scenario_b import run_scenario_b

        class MockAdapter(MemoryAdapter):
            """Mock adapter that returns canned responses for testing."""

            @property
            def name(self):
                """Return the mock adapter name."""
                return "Mock"

            def setup(self, uid):
                """No-op setup for the mock adapter."""

            def store(self, content, metadata=None):
                """Return a successful store result with fake latency."""

                return MemoryResult(True, 5.0, len(content.split())*2)

            def retrieve(self, query, limit=5):
                """Return a successful retrieve result with a mock memory."""

                return MemoryResult(True, 3.0, 100, ["mock"])

            def update(self, mid, content):
                """Return a successful update result."""

                return MemoryResult(True, 5.0)

            def delete(self, mid):
                """Return a successful delete result."""

                return MemoryResult(True, 2.0)

            def get_all(self):
                """Return an empty list of memories."""

                return MemoryResult(True, 1.0, data=[])

            def cleanup(self):
                """No-op cleanup for the mock adapter."""

        evaluator = LLMEvaluator(api_key="")
        adapter = MockAdapter()
        metrics = run_scenario_b(adapter, evaluator, dry_run=True)
        assert metrics.total_store_calls > 0
        assert metrics.total_retrieve_calls > 0

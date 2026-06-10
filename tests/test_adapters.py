"""Tests for the benchmark adapter interfaces and evaluator."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.base import MemoryAdapter, MemoryResult, BenchmarkMetric
from benchmarks.evaluator import LLMEvaluator


# ── MemoryResult tests ──

class TestMemoryResult:
    def test_success_result(self):
        r = MemoryResult(success=True, latency_ms=42.5, tokens_used=100, data="ok")
        assert r.success is True
        assert r.latency_ms == 42.5
        assert r.tokens_used == 100

    def test_failure_result(self):
        r = MemoryResult(success=False, latency_ms=0, error="connection refused")
        assert r.success is False
        assert r.error == "connection refused"


# ── BenchmarkMetric tests ──

class TestBenchmarkMetric:
    def test_empty_metric(self):
        m = BenchmarkMetric(framework="Test", scenario="S1")
        assert m.store_p95_latency == 0.0
        assert m.retrieve_p95_latency == 0.0
        assert m.mean_retrieval_accuracy == 0.0

    def test_p95_latency(self):
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.store_latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        assert m.store_p95_latency == 100.0  # 95th percentile of 10 items

    def test_mean_accuracy(self):
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.retrieval_scores = [0.8, 0.9, 0.7]
        assert abs(m.mean_retrieval_accuracy - 0.8) < 0.01

    def test_to_dict(self):
        m = BenchmarkMetric(framework="Test", scenario="S1")
        m.store_latencies = [10, 20]
        d = m.to_dict()
        assert d["framework"] == "Test"
        assert d["scenario"] == "S1"
        assert "store_p95_latency_ms" in d
        assert "retrieval_accuracy" in d


# ── LLMEvaluator tests ──

class TestLLMEvaluator:
    def test_keyword_score_perfect_match(self):
        score, reasoning = LLMEvaluator._keyword_score(
            "the cat sat on the mat",
            ["the cat sat on the mat and looked around"],
        )
        assert score == 1.0
        assert "overlap" in reasoning.lower()

    def test_keyword_score_partial_match(self):
        score, reasoning = LLMEvaluator._keyword_score(
            "the quick brown fox jumps over the lazy dog",
            ["the fox jumped over a dog"],
        )
        assert 0.0 < score < 1.0

    def test_keyword_score_no_match(self):
        score, reasoning = LLMEvaluator._keyword_score(
            "machine learning neural network",
            ["pizza pasta carbonara recipe"],
        )
        assert score == 0.0

    def test_keyword_score_empty_golden(self):
        score, _ = LLMEvaluator._keyword_score("", ["some text"])
        assert score == 0.0

    def test_evaluator_without_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        evaluator = LLMEvaluator()
        assert evaluator.client is None
        # Should fall back to keyword scoring
        score, _ = evaluator.score_retrieval(
            "test query", "test answer", ["test answer is here"]
        )
        assert score > 0


# ── Integration: dry-run scenario A ──

class TestDryRunScenarioA:
    def test_dry_run_loads_dataset(self):
        from benchmarks.scenario_a import load_dataset
        dataset = load_dataset()
        assert len(dataset) == 10
        assert "content" in dataset[0]
        assert "retrieval_queries" in dataset[0]

    def test_dry_run_scenario_a(self):
        """Run Scenario A in dry-run mode with a mock adapter."""
        class MockAdapter(MemoryAdapter):
            @property
            def name(self): return "Mock"
            def setup(self, uid): pass
            def store(self, content, metadata=None):
                return MemoryResult(True, 5.0, len(content.split())*2)
            def retrieve(self, query, limit=5):
                return MemoryResult(True, 3.0, 100, ["mock memory"])
            def update(self, mid, content):
                return MemoryResult(True, 5.0)
            def delete(self, mid):
                return MemoryResult(True, 2.0)
            def get_all(self):
                return MemoryResult(True, 1.0, data=[])
            def cleanup(self): pass

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


# ── Integration: dry-run scenario B ──

class TestDryRunScenarioB:
    def test_dry_run_loads_dataset(self):
        from benchmarks.scenario_b import load_dataset
        dataset = load_dataset()
        assert len(dataset) == 4
        assert "session_id" in dataset[0]
        assert "evaluation_queries" in dataset[0]

    def test_dry_run_scenario_b(self):
        from benchmarks.scenario_b import run_scenario_b
        class MockAdapter(MemoryAdapter):
            @property
            def name(self): return "Mock"
            def setup(self, uid): pass
            def store(self, content, metadata=None):
                return MemoryResult(True, 5.0, len(content.split())*2)
            def retrieve(self, query, limit=5):
                return MemoryResult(True, 3.0, 100, ["mock"])
            def update(self, mid, content):
                return MemoryResult(True, 5.0)
            def delete(self, mid):
                return MemoryResult(True, 2.0)
            def get_all(self):
                return MemoryResult(True, 1.0, data=[])
            def cleanup(self): pass

        evaluator = LLMEvaluator(api_key="")
        adapter = MockAdapter()
        metrics = run_scenario_b(adapter, evaluator, dry_run=True)
        assert metrics.total_store_calls > 0
        assert metrics.total_retrieve_calls > 0

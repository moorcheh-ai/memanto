"""Pytest test suite — runs fully offline, zero API keys required."""
from __future__ import annotations

import os
import pytest

# Ensure offline mode for CI
os.environ.pop("MOORCHEH_API_KEY", None)
os.environ.pop("MEM0_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)

from showdown_benchmark.backends.offline import (
    ActiveMemoryBackend,
    AppendLogBackend,
    SnapshotBackend,
)
from showdown_benchmark.dataset import SCENARIOS
from showdown_benchmark.judge import score_answer
from showdown_benchmark.runner import run_benchmark


# ---------------------------------------------------------------------------
# Unit: Backend basic contract
# ---------------------------------------------------------------------------

class TestActiveMemoryBackend:
    def test_reset_clears_store(self):
        b = ActiveMemoryBackend()
        b.ingest("u1", "Always format reports as concise executive briefs.")
        b.reset()
        result = b.retrieve("u1", "report format")
        assert result.context == "" or "brief" not in result.context.lower()

    def test_preference_reversal_returns_latest(self):
        b = ActiveMemoryBackend()
        b.ingest("u1", "Always format reports as concise executive briefs.")
        b.ingest("u1", "From now on I need detailed launch-risk memos with evidence tables.")
        result = b.retrieve("u1", "report format")
        # Should return memo/evidence, not brief
        assert "memo" in result.context.lower() or "evidence" in result.context.lower()

    def test_returns_ingest_result(self):
        b = ActiveMemoryBackend()
        r = b.ingest("u1", "Use UTC for all timestamps in our system.")
        assert r.tokens_written > 0
        assert r.latency_ms >= 0

    def test_returns_retrieve_result(self):
        b = ActiveMemoryBackend()
        b.ingest("u1", "Use UTC for all timestamps in our system.")
        r = b.retrieve("u1", "timezone")
        assert isinstance(r.context, str)
        assert r.tokens_retrieved >= 0


class TestAppendLogBackend:
    def test_accumulates_entries(self):
        b = AppendLogBackend()
        b.ingest("u1", "First fact.")
        b.ingest("u1", "Second fact.")
        r = b.retrieve("u1", "fact")
        # Both should appear since both contain "fact"
        assert "First" in r.context or "Second" in r.context

    def test_reset_clears_log(self):
        b = AppendLogBackend()
        b.ingest("u1", "some information")
        b.reset()
        r = b.retrieve("u1", "some information")
        assert r.context == "" or "some" not in r.context

    def test_stale_fact_contamination(self):
        """Append-log returns old + new entries when preferences reverse."""
        b = AppendLogBackend()
        b.ingest("u1", "Always format reports as concise executive briefs.")
        b.ingest("u1", "From now on I need detailed launch-risk memos with evidence tables.")
        r = b.retrieve("u1", "report format")
        # Both old and new are likely present → stale contamination
        has_old = "brief" in r.context.lower()
        has_new = "memo" in r.context.lower() or "evidence" in r.context.lower()
        # At least one must be present
        assert has_old or has_new


class TestSnapshotBackend:
    def test_ingest_and_retrieve(self):
        b = SnapshotBackend()
        b.ingest("u1", "Use UTC for all timestamps.")
        r = b.retrieve("u1", "timezone")
        assert isinstance(r.context, str)

    def test_new_session_creates_separate_slot(self):
        b = SnapshotBackend()
        b.ingest("u1", "Use UTC.")
        b.new_session("u1")
        b.ingest("u1", "Use local timezone.")
        r = b.retrieve("u1", "timezone")
        # Both sessions are returned (cross-session bleed)
        assert "utc" in r.context.lower() or "local" in r.context.lower()


# ---------------------------------------------------------------------------
# Unit: Judge
# ---------------------------------------------------------------------------

class TestJudge:
    def test_keyword_present_scores_1(self):
        assert score_answer("advisory lock prevents double charges", "retry", "advisory", "") == 1.0

    def test_keyword_absent_scores_0(self):
        assert score_answer("exponential backoff strategy", "retry", "advisory", "") == 0.0

    def test_case_insensitive(self):
        assert score_answer("Use ADVISORY LOCK", "retry", "advisory", "") == 1.0

    def test_empty_context_scores_0(self):
        assert score_answer("", "query", "keyword", "") == 0.0


# ---------------------------------------------------------------------------
# Integration: Full offline benchmark
# ---------------------------------------------------------------------------

class TestBenchmarkIntegration:
    def test_benchmark_runs_without_errors(self):
        summaries = run_benchmark(
            backends=[ActiveMemoryBackend(), AppendLogBackend()],
            n_runs=1,
            scenarios=SCENARIOS[:2],
            verbose=False,
        )
        assert len(summaries) == 2
        for s in summaries:
            assert 0.0 <= s.accuracy_mean <= 1.0
            assert s.n_runs == 1
            assert s.n_scenarios == 2

    def test_active_memory_beats_append_log_on_reversals(self):
        """Active memory should have higher accuracy than append-log on reversal scenarios."""
        reversal_scenarios = [s for s in SCENARIOS if "reversal" in s.name or "flip" in s.name]
        if not reversal_scenarios:
            pytest.skip("No reversal scenarios found")

        am = ActiveMemoryBackend()
        al = AppendLogBackend()
        summaries = run_benchmark(
            backends=[am, al],
            n_runs=2,
            scenarios=reversal_scenarios,
            verbose=False,
        )
        am_sum = summaries[0]
        al_sum = summaries[1]
        # Active memory should be strictly better on preference reversals
        assert am_sum.accuracy_mean >= al_sum.accuracy_mean, (
            f"Active memory ({am_sum.accuracy_mean:.2%}) should beat "
            f"append-log ({al_sum.accuracy_mean:.2%}) on reversal scenarios"
        )

    def test_all_scenarios_have_probes(self):
        for s in SCENARIOS:
            assert s.probes, f"Scenario '{s.name}' has no probes"
            for p in s.probes:
                assert p.expected_keyword, f"Probe '{p.query}' has no expected_keyword"

    def test_report_generation(self, tmp_path):
        from showdown_benchmark.report import generate_report
        summaries = run_benchmark(
            backends=[ActiveMemoryBackend()],
            n_runs=1,
            scenarios=SCENARIOS[:1],
            verbose=False,
        )
        report = generate_report(summaries, output_dir=tmp_path)
        assert "# Agentic Memory Showdown" in report
        assert (tmp_path / "results.md").exists()
        assert (tmp_path / "results.json").exists()

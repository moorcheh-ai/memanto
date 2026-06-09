import pytest

import productivity_benchmark
from productivity_benchmark import run_benchmark


def test_benchmark_proves_no_repeated_architecture_instructions(tmp_path):
    """The second skill session should recover every required instruction."""

    result = run_benchmark(tmp_path / "benchmark-memory.jsonl")

    assert result["saved_memories"] == 3
    assert result["candidate_memories"] == 5
    assert result["recalled_memories"] == 3
    assert result["repeated_instructions"] == 0


def test_benchmark_cleans_store_when_run_fails(tmp_path, monkeypatch):
    """A failed benchmark should not leave its local JSONL artefact behind."""

    monkeypatch.chdir(tmp_path)

    def fail_benchmark(store):
        store.write_text("partial", encoding="utf-8")
        raise RuntimeError("benchmark failed")

    monkeypatch.setattr(productivity_benchmark, "run_benchmark", fail_benchmark)

    with pytest.raises(RuntimeError, match="benchmark failed"):
        productivity_benchmark.main()

    assert not (tmp_path / ".memanto-skills-benchmark.jsonl").exists()

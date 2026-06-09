from productivity_benchmark import run_benchmark


def test_benchmark_proves_no_repeated_architecture_instructions(tmp_path):
    """The second skill session should recover every required instruction."""

    result = run_benchmark(tmp_path / "benchmark-memory.jsonl")

    assert result["saved_memories"] == 3
    assert result["recalled_memories"] == 3
    assert result["repeated_instructions"] == 0

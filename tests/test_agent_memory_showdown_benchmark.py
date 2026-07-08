from pathlib import Path

from benchmarks.agent_memory_showdown.run_benchmark import (
    AppendOnlyKeywordAdapter,
    StatefulCompactionAdapter,
    load_dataset,
    run_suite,
    summarize,
    write_outputs,
)


def test_agent_memory_showdown_dataset_runs(tmp_path):
    dataset = Path("benchmarks/agent_memory_showdown/dataset.jsonl")
    cases = load_dataset(dataset)

    results = run_suite(
        cases,
        [
            StatefulCompactionAdapter(),
            AppendOnlyKeywordAdapter(),
        ],
    )
    summary = summarize(results)

    assert set(summary) == {"stateful_compaction", "append_only_keyword"}
    assert summary["stateful_compaction"]["query_count"] == 6
    assert 0 <= summary["append_only_keyword"]["accuracy"] <= 1
    assert (
        summary["stateful_compaction"]["accuracy"]
        >= summary["append_only_keyword"]["accuracy"]
    )

    write_outputs(results, tmp_path)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "results.csv").exists()


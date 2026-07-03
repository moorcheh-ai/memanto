import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "memanto_memory_benchmark.py"
SPEC = importlib.util.spec_from_file_location("memanto_memory_benchmark", SCRIPT_PATH)
assert SPEC is not None
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_score_question_rewards_expected_terms_and_penalizes_forbidden_terms():
    question = benchmark.BenchmarkQuestion(
        id="q",
        query="What indentation style is current?",
        expected_terms=("4 spaces",),
        forbidden_terms=("tabs",),
        top_k=1,
    )

    good = benchmark.score_question(
        question,
        [benchmark.RecalledMemory("The current preference is 4 spaces.")],
    )
    stale = benchmark.score_question(
        question,
        [benchmark.RecalledMemory("The old preference was tabs.")],
    )

    assert good["score"] == 1.0
    assert stale["score"] == 0.0
    assert stale["forbidden_hits"] == ["tabs"]


def test_default_dataset_loads_from_examples_directory():
    dataset = benchmark.load_dataset()

    assert dataset.name == "agent_memory_showdown_dynamic_preferences_v1"
    assert len(dataset.memories) >= 5
    assert len(dataset.questions) >= 5
    assert any("4 spaces" in question.expected_terms for question in dataset.questions)


def test_offline_benchmark_reports_accuracy_and_resource_footprint():
    dataset = benchmark.load_dataset()
    report = benchmark.run_benchmark(
        dataset,
        ["memanto-offline", "lexical-baseline"],
    )

    results = {result["framework"]: result for result in report["results"]}
    assert set(results) == {"memanto-offline", "lexical-baseline"}
    assert results["memanto-offline"]["accuracy"] >= results["lexical-baseline"]["accuracy"]

    footprint = results["memanto-offline"]["resource_footprint"]
    assert footprint["estimated_tokens_ingested"] > 0
    assert footprint["estimated_tokens_retrieved"] > 0
    assert "p95_recall_latency_ms" in footprint


def test_cli_writes_json_report(tmp_path, capsys):
    output_path = tmp_path / "benchmark-report.json"

    exit_code = benchmark.main(
        [
            "--frameworks",
            "memanto-offline,lexical-baseline",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "memanto-offline" in captured.out
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["dataset"]["question_count"] >= 5
    assert len(data["results"]) == 2

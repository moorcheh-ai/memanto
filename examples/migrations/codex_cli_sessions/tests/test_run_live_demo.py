from __future__ import annotations

import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from run_live_demo import (  # noqa: E402
    _load_golden_cases,
    _show_okf_preview,
    build_command_plan,
    main,
    verify_live_results,
)


class _Transcript:
    def __init__(self) -> None:
        self.text = ""

    def write(self, value: str) -> None:
        self.text += value

    def flush(self) -> None:
        pass


def test_live_plan_uses_shipped_cli_for_complete_freedom_loop(
    tmp_path: Path,
) -> None:
    questions = ["Question one?", "Question two?"]
    plan = build_command_plan(
        memanto_bin="memanto",
        agent_id="codex-okf-test",
        bundle=tmp_path / "sample_okf",
        portable_output=tmp_path / "portable_okf",
        questions=questions,
        answer_count=1,
    )

    labels = [label for label, _ in plan]
    assert labels == [
        "create_empty_agent",
        "before_recall_1",
        "before_recall_2",
        "import_okf",
        "after_recall_1",
        "after_recall_2",
        "after_answer_1",
        "export_portable_okf",
    ]
    import_command = dict(plan)["import_okf"]
    assert import_command[:4] == [
        "memanto",
        "migrate",
        "okf",
        str(tmp_path / "sample_okf"),
    ]
    assert import_command[-2:] == ["--agent", "codex-okf-test"]
    export_command = dict(plan)["export_portable_okf"]
    assert export_command[-1] == "--okf"
    assert "--output" in export_command


def test_live_demo_fails_cleanly_without_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    assert main(["--output", str(tmp_path / "evidence")]) == 2
    assert not (tmp_path / "evidence").exists()


def test_golden_cases_derive_exact_titles_from_sample_okf() -> None:
    bundle = EXAMPLE_DIR / "sample_okf"
    cases = _load_golden_cases(bundle / "golden_questions.json", bundle)

    assert len(cases) == 5
    assert cases[0]["id"] == "memo-ambiguity"
    assert cases[0]["expected_title"] == "Codex assistant memory 003"
    assert cases[-1]["expected_title"] == "Codex assistant memory 014"


def test_live_result_verification_checks_empty_then_exact_recall_and_rag() -> None:
    cases = [
        {
            "id": "proof",
            "question": "What happened?",
            "expected_title": "Codex assistant memory 003",
        }
    ]
    results = [
        {"label": "before_recall_1", "_stdout": "No memories found"},
        {
            "label": "after_recall_1",
            "_stdout": "Found 1 memories\nCodex assistant memory 003",
        },
        {
            "label": "after_answer_1",
            "_stdout": "Used 1 memories\nCodex assistant memory 003",
        },
    ]

    report = verify_live_results(results, cases, answer_count=1)
    assert report["verified"] is True
    assert report["recall_passed"] == report["recall_total"] == 1
    assert report["rag_context_passed"] == report["rag_context_total"] == 1

    results[-1]["_stdout"] = "Used unrelated memory"
    failed = verify_live_results(results, cases, answer_count=1)
    assert failed["verified"] is False


def test_live_demo_prints_readable_portable_okf(tmp_path: Path, capsys) -> None:
    root = tmp_path / "portable_okf"
    memory_dir = root / "memories" / "conversation"
    memory_dir.mkdir(parents=True)
    (root / "memories" / "index.md").write_text(
        "# Portable memory index\n", encoding="utf-8"
    )
    (memory_dir / "decision.md").write_text(
        '---\ntitle: "Readable decision"\n---\n\nOwned memory.\n',
        encoding="utf-8",
    )
    transcript = _Transcript()

    previews = _show_okf_preview(root, transcript)

    assert [item["path"] for item in previews] == [
        "memories/index.md",
        "memories/conversation/decision.md",
    ]
    assert "Readable decision" in transcript.text
    assert "Owned memory." in capsys.readouterr().out

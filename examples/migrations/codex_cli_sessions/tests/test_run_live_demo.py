from __future__ import annotations

import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from run_live_demo import build_command_plan, main  # noqa: E402


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

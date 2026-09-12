from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "langmem_live_workflow", Path(__file__).parents[1] / "live_workflow.py"
)
assert SPEC and SPEC.loader
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int = 1
) -> tuple[Path, Path, Path]:
    records = [
        {"namespace": ["n"], "key": f"k-{index}", "value": {"content": "fact"}}
        for index in range(count)
    ]
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"memories": records}), encoding="utf-8")
    bundle = tmp_path / "bundle"
    from examples.migrations.langmem import run

    run.to_okf(json.loads(source.read_text()), bundle)
    monkeypatch.setenv("MOORCHEH_API_KEY", "offline-test-key")
    monkeypatch.setattr(live.Path, "home", staticmethod(lambda: tmp_path))

    class Config:
        def get_active_session(self) -> tuple[str, str]:
            return "demo", "token"

    monkeypatch.setattr(live, "ConfigManager", Config)
    monkeypatch.setattr(live, "SdkClient", lambda key: SimpleNamespace())
    monkeypatch.setattr(live, "recall_report", lambda client, agent, queries: [])
    report = tmp_path / "run-report.json"
    report.write_text(json.dumps({"source_retrieval": []}), encoding="utf-8")
    output = tmp_path / "nested" / "result"
    return source, bundle, output


def _fake_commands(
    monkeypatch: pytest.MonkeyPatch,
    bundle: Path,
    *,
    mismatch: bool = False,
    extra: bool = False,
):
    calls: list[list[str]] = []

    def command(command: list[str], cwd: Path) -> tuple[float, str]:
        calls.append(command)
        if "export" in command:
            export = Path(command[command.index("--output") + 1])
            from examples.migrations.langmem import run

            records = json.loads((bundle.parent / "source.json").read_text())[
                "memories"
            ]
            if mismatch:
                records[0] = {**records[0], "value": {"content": "changed"}}
            if extra:
                records.append(
                    {
                        "namespace": ["n"],
                        "key": "extra",
                        "value": {"content": "sentinel"},
                    }
                )
            limit = int(command[command.index("--limit") + 1])
            run.to_okf({"memories": records[:limit]}, export)
        return 0.1, "ok\n"

    monkeypatch.setattr(live, "run_command", command)
    return calls


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    source: Path,
    bundle: Path,
    output: Path,
    *extra: str,
) -> None:
    monkeypatch.setattr(
        live.sys,
        "argv",
        [
            "live_workflow.py",
            "--bundle",
            str(bundle),
            "--source-export",
            str(source),
            "--source-report",
            str(source.with_name("run-report.json")),
            "--agent",
            "demo",
            "--output",
            str(output),
            "--allow-shared-config",
            *extra,
        ],
    )
    live.main()


def test_export_failure_removes_final_and_staging_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch)

    def fail_export(command: list[str], cwd: Path) -> tuple[float, str]:
        if "export" in command:
            raise RuntimeError("export failed")
        return 0.1, "imported\n"

    calls = []
    monkeypatch.setattr(
        live,
        "run_command",
        lambda command, cwd: (calls.append(command) or fail_export(command, cwd)),
    )
    with pytest.raises(RuntimeError, match="export failed"):
        _invoke(monkeypatch, source, bundle, output)
    assert not output.exists()
    assert not list(output.parent.glob(f".{output.name}.staging-*"))
    assert sum("migrate" in call for call in calls) == 1


def test_retry_after_import_uses_resume_and_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch)
    calls = _fake_commands(monkeypatch, bundle)
    original = live.run_command
    failed = True

    def fail_once(command: list[str], cwd: Path) -> tuple[float, str]:
        nonlocal failed
        if "export" in command and failed:
            failed = False
            raise RuntimeError("export failed")
        return original(command, cwd)

    monkeypatch.setattr(live, "run_command", fail_once)
    with pytest.raises(RuntimeError, match="export failed"):
        _invoke(monkeypatch, source, bundle, output)
    _invoke(monkeypatch, source, bundle, output, "--resume-after-import")
    assert output.is_dir()
    assert sum("migrate" in call for call in calls) == 1
    report = json.loads((output / "live-report.json").read_text())
    assert report["snapshot_comparison"]["exact_match"] is True
    assert report["import"]["skipped"] is True
    assert report["import"]["seconds"] is None
    assert "Import skipped" in (output / "cli-import.txt").read_text()
    assert report["target_recall"] == json.loads(
        (output / "target-recall.json").read_text()
    )
    assert (output / "target-okf" / "index.md").is_file()
    assert not list(output.parent.glob(f".{output.name}.staging-*"))


@pytest.mark.parametrize("extra", [(), ("--resume-after-import",)])
def test_snapshot_mismatch_cleans_staging_and_prints_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: tuple[str, ...],
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch)
    _fake_commands(monkeypatch, bundle, mismatch=True)
    with pytest.raises(SystemExit, match="snapshot comparison"):
        _invoke(monkeypatch, source, bundle, output, *extra)
    assert not output.exists()
    assert not list(output.parent.glob(f".{output.name}.staging-*"))
    assert '"exact_match": false' in capsys.readouterr().out


def test_existing_destination_is_preserved_without_cli_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch)
    output.mkdir(parents=True)
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    calls = _fake_commands(monkeypatch, bundle)
    with pytest.raises(FileExistsError):
        _invoke(monkeypatch, source, bundle, output)
    assert marker.read_text(encoding="utf-8") == "keep"
    assert calls == []


@pytest.mark.parametrize("count, expected_limit", [(0, 1), (99, 100)])
def test_export_limit_includes_unexpected_record_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    expected_limit: int,
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch, count=count)
    calls = _fake_commands(monkeypatch, bundle)
    _invoke(monkeypatch, source, bundle, output)
    export = next(call for call in calls if "export" in call)
    assert export[export.index("--limit") + 1] == str(expected_limit)


@pytest.mark.parametrize("count", [100, 101])
def test_export_limit_above_cli_maximum_is_rejected_before_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch, count=count)
    calls = _fake_commands(monkeypatch, bundle)
    with pytest.raises(ValueError, match="maximum is 100"):
        _invoke(monkeypatch, source, bundle, output)
    assert calls == []
    assert not output.exists()


@pytest.mark.parametrize("extra", [(), ("--resume-after-import",)])
def test_export_limit_detects_unexpected_same_type_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: tuple[str, ...],
) -> None:
    source, bundle, output = _prepare(tmp_path, monkeypatch)
    calls = _fake_commands(monkeypatch, bundle, extra=True)
    with pytest.raises(SystemExit, match="snapshot comparison"):
        _invoke(monkeypatch, source, bundle, output, *extra)
    comparison = json.loads(capsys.readouterr().out)["snapshot_comparison"]
    assert comparison["exact_match"] is False
    assert comparison["unexpected"] == [live.canonical([["n"], "extra"])]
    assert comparison["missing"] == comparison["changed"] == []
    assert not output.exists()
    assert calls and calls[-1][calls[-1].index("--limit") + 1] == "2"

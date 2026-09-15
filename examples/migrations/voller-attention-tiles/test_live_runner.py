"""Offline regressions for the live runner; no service credentials are used."""

import json
import subprocess
from pathlib import Path

import pytest
import run_live
from adapter import build_bundle, restore_bundle
from fastapi import HTTPException
from run_live import (
    collect_agent_evidence,
    collect_ready_agent_evidence,
    export_and_copy,
    retrieval_scores,
    run_cli,
    wait_for_complete_export,
)
from test_adapter import catalog

from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


@pytest.mark.parametrize("tile_count", [0, 2, 100, 101, 150])
def test_live_export_uses_native_directory_before_collecting(
    tmp_path, monkeypatch, tile_count
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    source = tmp_path / "source"
    data = catalog()
    data["tiles"] = [
        dict(data["tiles"][0], id=f"tile-{i}", title=f"Concept {i}")
        for i in range(tile_count)
    ]
    build_bundle(data, source)
    grouped = {}
    for i, row in enumerate(map_okf(load_okf_bundle(source))):
        grouped.setdefault(row["type"], []).append(dict(row, id=f"test-{i}"))
    destination = tmp_path / "workflow-evidence" / "first_export"
    service = OkfExportService()

    # Reproduce the observed failure against the real path validator.
    with pytest.raises(HTTPException, match="output_path must be inside"):
        service.write_okf_bundle("test-agent", grouped, output_dir=destination)

    calls = []

    def command(label, *parts):
        calls.append((label, parts))
        assert "--output" not in parts
        assert parts == (
            "memory",
            "export",
            "--okf",
            "--agent",
            "test-agent",
            "--limit",
            str(tile_count + 1),
            "--split",
            "file",
        )
        # Exercise actual serialization at the CLI's default destination.
        # Model the CLI's per-type selection, then exercise the actual native
        # serializer and full-snapshot restoration (including >100 artifacts).
        limit = int(parts[parts.index("--limit") + 1])
        selected = {kind: records[:limit] for kind, records in grouped.items()}
        service.write_okf_bundle("test-agent", selected, split="file")

    export_and_copy(command, "04_export", "test-agent", destination, data)
    assert len(calls) == 1
    assert restore_bundle(destination) == data
    assert restore_bundle(service.exports_dir / "test-agent_okf") == data


def test_failed_command_is_visible_without_exposing_key(tmp_path, monkeypatch, capsys):
    sentinel = "synthetic-test-credential"

    def failed_command(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            1,
            stdout=f"key={sentinel}\n",
            stderr="::error::export destination rejected\n",
        )

    monkeypatch.setattr(subprocess, "run", failed_command)
    with pytest.raises(RuntimeError, match="04_export failed"):
        run_cli(tmp_path, "04_export", "memory", "export", key=sentinel)
    captured = capsys.readouterr()
    saved = (tmp_path / "04_export.txt").read_text()
    assert sentinel not in captured.err + saved
    assert "[REDACTED]" in captured.err and "[REDACTED]" in saved
    assert "[04_export] ::error::export destination rejected" in captured.err


@pytest.mark.parametrize("complete_export", [True, False])
def test_recall_diagnostics_preserve_misses_and_require_complete_export(
    tmp_path, monkeypatch, capsys, complete_export
):
    data = catalog()
    target = data["tiles"][0]["id"]
    probes = [{"query": "Synthetic named-record question", "expected_id": target}]
    calls = []

    def recall(agent, query):
        calls.append("recall")
        return [] if len(calls) == 1 else [target]

    def export(command, label, agent, destination, source_data):
        calls.append("export")
        exported = dict(data)
        if not complete_export:
            exported["tiles"] = data["tiles"][1:]
        build_bundle(exported, destination)

    monkeypatch.setattr(run_live, "remote_recall", recall)
    monkeypatch.setattr(run_live, "export_and_copy", export)

    def collect():
        collect_agent_evidence(
            lambda *args: None,
            "04_export",
            "test-agent",
            tmp_path / "export",
            data,
            probes,
            "first",
        )

    if complete_export:
        collect()
        assert calls == ["recall", "export", "recall"]
        assert probes[0]["first_after_verified_export_top5"] == [target]
    else:
        with pytest.raises(AssertionError, match="did not preserve"):
            collect()
        assert calls == ["recall", "export"]
        assert "first_after_verified_export_top5" not in probes[0]
    assert probes[0]["first_memanto_top5"] == []
    assert (tmp_path / "first_recall.json").exists()
    assert '"returned_ids": []' in capsys.readouterr().out


def test_later_recall_success_does_not_erase_original_failure():
    probes = [
        {
            "expected_id": f"tile-{i}",
            "source_top5": [f"tile-{i}"],
            "first_memanto_top5": [] if i < 2 else [f"tile-{i}"],
            "second_memanto_top5": [f"tile-{i}"],
            "first_after_verified_export_top5": [f"tile-{i}"],
            "second_after_verified_export_top5": [f"tile-{i}"],
        }
        for i in range(8)
    ]
    scores = retrieval_scores(probes)
    assert scores["first_memanto_top5"] == 6
    assert scores["first_after_verified_export_top5"] == 8
    assert not all(value == 8 for value in scores.values())


def test_ready_queries_wait_for_two_consecutive_complete_snapshots(
    tmp_path, monkeypatch
):
    data = catalog()
    complete = iter([False, True, False, True, True])
    calls = []
    monkeypatch.setattr(run_live.time, "sleep", lambda seconds: None)

    def export(command, label, agent, destination, source_data):
        calls.append("export")
        snapshot = dict(data)
        if not next(complete):
            snapshot["tiles"] = data["tiles"][1:]
        build_bundle(snapshot, destination)

    def recall(agent, query):
        # Readiness never asks the scored question; scoring happens just once.
        assert calls == ["export"] * 5
        calls.append("recall")
        return []

    monkeypatch.setattr(run_live, "export_and_copy", export)
    monkeypatch.setattr(run_live, "remote_recall", recall)
    probes = [{"query": "Scored question", "expected_id": data["tiles"][0]["id"]}]
    evidence = collect_ready_agent_evidence(
        lambda *args: None, "04", "agent", tmp_path / "export", data, probes, "first"
    )
    assert calls == ["export"] * 5 + ["recall"]
    assert evidence["ready"]
    assert len(evidence["observations"]) == 5
    assert restore_bundle(tmp_path / "export") == data
    # A semantic miss after the barrier still fails; it isn't retried until green.
    assert retrieval_scores(probes)["first_after_readiness_top5"] == 0


def test_incomplete_visibility_is_bounded_and_evidence_survives(tmp_path, monkeypatch):
    data = catalog()
    calls = []
    monkeypatch.setattr(run_live.time, "sleep", lambda seconds: None)

    def export(command, label, agent, destination, source_data):
        calls.append(label)
        build_bundle(dict(data, tiles=data["tiles"][1:]), destination)

    monkeypatch.setattr(run_live, "export_and_copy", export)
    with pytest.raises(TimeoutError, match="not confirmed"):
        wait_for_complete_export(
            lambda *args: None,
            "04",
            "agent",
            tmp_path / "export",
            data,
            max_attempts=3,
        )
    assert len(calls) == 3
    assert not (tmp_path / "export").exists()
    evidence = json.loads((tmp_path / "export_readiness/readiness.json").read_text())
    assert evidence["ready"] is False
    assert len(evidence["observations"]) == 3


def test_readiness_deadline_cannot_be_overridden_by_complete_data(
    tmp_path, monkeypatch
):
    data = catalog()
    clock = [0.0]
    monkeypatch.setattr(run_live.time, "monotonic", lambda: clock[0])

    def export(command, label, agent, destination, source_data):
        build_bundle(data, destination)
        clock[0] += 10

    monkeypatch.setattr(run_live, "export_and_copy", export)
    with pytest.raises(TimeoutError):
        wait_for_complete_export(
            lambda *args: None,
            "04",
            "agent",
            tmp_path / "export",
            data,
            timeout_seconds=5,
        )
    assert not (tmp_path / "export").exists()


def test_readiness_does_not_retry_cli_errors_or_score_after_them(tmp_path, monkeypatch):
    calls = []

    def export(*args):
        calls.append("export")
        raise RuntimeError("Authentication failure")

    def recall(*args):
        pytest.fail("Scoring must not run after a failed readiness check")

    monkeypatch.setattr(run_live, "export_and_copy", export)
    monkeypatch.setattr(run_live, "remote_recall", recall)
    with pytest.raises(RuntimeError, match="Authentication"):
        collect_ready_agent_evidence(
            lambda *args: None,
            "04",
            "agent",
            tmp_path / "export",
            catalog(),
            [{"query": "question", "expected_id": "target"}],
            "first",
        )
    assert calls == ["export"]

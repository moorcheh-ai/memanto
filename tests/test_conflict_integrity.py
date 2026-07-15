"""Regression tests for conflict report integrity and resolution safety."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memanto.app.utils.conflict_helpers import merge_conflict_reports


class TestMergeConflictReports:
    def test_preserves_resolved_conflicts(self):
        existing = [
            {
                "type": "contradiction",
                "title": "Database preference changed",
                "old_memory_id": "old-1",
                "new_memory_id": "new-1",
                "resolved": True,
                "resolution": "keep_new",
            }
        ]
        fresh = [
            {
                "type": "contradiction",
                "title": "Database preference changed",
                "old_memory_id": "old-1",
                "new_memory_id": "new-1",
                "resolved": False,
            },
            {
                "type": "duplicate",
                "title": "Repeated deployment note",
                "old_memory_id": "old-2",
                "new_memory_id": "new-2",
                "resolved": False,
            },
        ]

        merged = merge_conflict_reports(existing, fresh)

        assert len(merged) == 2
        assert merged[0]["resolved"] is True
        assert merged[0]["resolution"] == "keep_new"
        assert merged[1]["title"] == "Repeated deployment note"


def test_conflict_regeneration_preserves_resolved_entries(tmp_path, monkeypatch):
    """Re-running conflict detection must not erase prior user resolutions."""
    from memanto.app.services import daily_analysis_service as module

    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    conflicts_dir = tmp_path / ".memanto" / "conflicts"
    sessions_dir.mkdir()
    conflicts_dir.mkdir(parents=True)

    (sessions_dir / "agent-1_2026-07-15_001_summary.md").write_text(
        "# Session\n\nUser switched from PostgreSQL to MongoDB.",
        encoding="utf-8",
    )

    existing_report = [
        {
            "type": "contradiction",
            "title": "Database preference changed",
            "old_memory_id": "old-db",
            "new_memory_id": "new-db",
            "resolved": True,
            "resolution": "keep_new",
        },
        {
            "type": "duplicate",
            "title": "Repeated deploy note",
            "old_memory_id": "old-dup",
            "new_memory_id": "new-dup",
            "resolved": False,
        },
    ]
    json_path = conflicts_dir / "agent-1_2026-07-15_conflicts.json"
    json_path.write_text(json.dumps(existing_report), encoding="utf-8")

    client = MagicMock()
    client.answer.generate.return_value = {
        "answer": json.dumps(
            [
                {
                    "type": "contradiction",
                    "title": "Database preference changed",
                    "old_memory_id": "old-db",
                    "new_memory_id": "new-db",
                    "description": "Re-detected contradiction",
                    "recommendation": "keep_new",
                }
            ]
        )
    }
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )
    result = service.generate_conflict_report("agent-1", "2026-07-15")

    assert result["status"] == "success"
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved[0]["resolved"] is True
    assert saved[0]["resolution"] == "keep_new"
    assert any(item.get("title") == "Database preference changed" for item in saved)


@pytest.fixture
def conflict_report_file(tmp_path: Path) -> Path:
    conflicts_dir = tmp_path / ".memanto" / "conflicts"
    conflicts_dir.mkdir(parents=True)
    report = [
        {
            "type": "contradiction",
            "title": "Conflicting preference",
            "old_memory_id": "old-1",
            "new_memory_id": "new-1",
            "resolved": False,
        }
    ]
    json_path = conflicts_dir / "agent-1_2026-07-15_conflicts.json"
    json_path.write_text(json.dumps(report), encoding="utf-8")
    return json_path


def test_resolve_conflict_fails_when_delete_returns_false(
    tmp_path, monkeypatch, conflict_report_file
):
    """Resolution must stay unresolved when target memories were not deleted."""
    from memanto.cli.client.direct_client import DirectClient

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    client = DirectClient(api_key="test-key")
    write_service = MagicMock()
    write_service.delete_memory.return_value = False

    with patch.object(client, "_get_write_service", return_value=write_service):
        with patch.object(client, "get_agent", return_value={"agent_id": "agent-1"}):
            result = client.resolve_conflict(
                agent_id="agent-1",
                date="2026-07-15",
                conflict_index=0,
                action="keep_new",
            )

    assert result["status"] == "failed"
    assert "warning_old" in result

    saved = json.loads(conflict_report_file.read_text(encoding="utf-8"))
    assert saved[0]["resolved"] is False


def test_resolve_conflict_marks_resolved_when_delete_succeeds(
    tmp_path, monkeypatch, conflict_report_file
):
    from memanto.cli.client.direct_client import DirectClient

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    client = DirectClient(api_key="test-key")
    write_service = MagicMock()
    write_service.delete_memory.return_value = True

    with patch.object(client, "_get_write_service", return_value=write_service):
        with patch.object(client, "get_agent", return_value={"agent_id": "agent-1"}):
            result = client.resolve_conflict(
                agent_id="agent-1",
                date="2026-07-15",
                conflict_index=0,
                action="keep_new",
            )

    assert result["status"] == "resolved"
    saved = json.loads(conflict_report_file.read_text(encoding="utf-8"))
    assert saved[0]["resolved"] is True
    assert saved[0]["resolution"] == "keep_new"

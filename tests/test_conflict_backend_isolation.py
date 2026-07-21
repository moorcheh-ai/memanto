"""Regression tests for cloud/on-prem conflict-report isolation."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memanto.app.config import settings


def _write_conflicts(path: Path, title: str) -> None:
    """Write one unresolved conflict to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "type": "conflict",
                    "title": title,
                    "old_memory_id": "old-id",
                    "new_memory_id": "new-id",
                    "resolved": False,
                }
            ]
        ),
        encoding="utf-8",
    )


def test_onprem_conflict_generation_does_not_overwrite_cloud_report(
    tmp_path, monkeypatch
):
    """Generating an on-prem report must write beneath the on-prem data root."""
    from memanto.app.services import daily_analysis_service as module

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")

    cloud_report = (
        tmp_path / ".memanto" / "conflicts" / "agent-1_2026-07-21_conflicts.json"
    )
    _write_conflicts(cloud_report, "cloud sentinel")

    sessions_dir = tmp_path / ".memanto" / "on-prem" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "agent-1_2026-07-21_sess-1_summary.md").write_text(
        "# Session\n\nA changed preference.", encoding="utf-8"
    )

    backend = MagicMock()
    backend.answer.generate.return_value = {"answer": "[]"}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: backend)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: None)

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=tmp_path / ".memanto" / "on-prem" / "summaries",
    )
    result = service.generate_conflict_report("agent-1", "2026-07-21")

    onprem_report = (
        tmp_path
        / ".memanto"
        / "on-prem"
        / "conflicts"
        / "agent-1_2026-07-21_conflicts.json"
    )
    assert Path(result["json_path"]) == onprem_report
    assert json.loads(cloud_report.read_text(encoding="utf-8"))[0]["title"] == (
        "cloud sentinel"
    )
    assert json.loads(onprem_report.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "client_cls_path",
    [
        "memanto.cli.client.direct_client.DirectClient",
        "memanto.cli.client.sdk_client.SdkClient",
    ],
)
def test_clients_list_conflicts_from_active_backend(
    tmp_path, monkeypatch, client_cls_path
):
    """Both clients must ignore the other backend's same-named report."""
    from importlib import import_module

    module_name, class_name = client_cls_path.rsplit(".", 1)
    client_cls = getattr(import_module(module_name), class_name)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cloud_report = (
        tmp_path / ".memanto" / "conflicts" / "agent-1_2026-07-21_conflicts.json"
    )
    onprem_report = (
        tmp_path
        / ".memanto"
        / "on-prem"
        / "conflicts"
        / "agent-1_2026-07-21_conflicts.json"
    )
    _write_conflicts(cloud_report, "cloud conflict")
    _write_conflicts(onprem_report, "on-prem conflict")

    client = client_cls("test-key")
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    assert client.list_conflicts("agent-1", "2026-07-21")[0]["title"] == (
        "on-prem conflict"
    )

    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    assert client.list_conflicts("agent-1", "2026-07-21")[0]["title"] == (
        "cloud conflict"
    )


@pytest.mark.parametrize(
    "client_cls_path",
    [
        "memanto.cli.client.direct_client.DirectClient",
        "memanto.cli.client.sdk_client.SdkClient",
    ],
)
def test_clients_resolve_only_the_active_backend_report(
    tmp_path, monkeypatch, client_cls_path
):
    """Resolution must not mutate the other backend's conflict state."""
    from importlib import import_module

    module_name, class_name = client_cls_path.rsplit(".", 1)
    client_cls = getattr(import_module(module_name), class_name)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    cloud_report = (
        tmp_path / ".memanto" / "conflicts" / "agent-1_2026-07-21_conflicts.json"
    )
    onprem_report = (
        tmp_path
        / ".memanto"
        / "on-prem"
        / "conflicts"
        / "agent-1_2026-07-21_conflicts.json"
    )
    _write_conflicts(cloud_report, "cloud conflict")
    _write_conflicts(onprem_report, "on-prem conflict")

    client = client_cls("test-key")
    monkeypatch.setattr(client, "_get_write_service", lambda: MagicMock())
    result = client.resolve_conflict(
        "agent-1", "2026-07-21", conflict_index=0, action="keep_both"
    )

    assert result["status"] == "resolved"
    assert json.loads(onprem_report.read_text(encoding="utf-8"))[0]["resolved"] is True
    assert json.loads(cloud_report.read_text(encoding="utf-8"))[0]["resolved"] is False


@pytest.mark.parametrize(
    "client_cls_path",
    [
        "memanto.cli.client.direct_client.DirectClient",
        "memanto.cli.client.sdk_client.SdkClient",
    ],
)
@pytest.mark.parametrize(
    ("agent_id", "date"),
    [
        ("../outside", "2026-07-21"),
        ("agent-1", "../../outside"),
        ("agent-1", "not-a-date"),
    ],
)
def test_clients_reject_unsafe_conflict_report_paths(
    tmp_path, monkeypatch, client_cls_path, agent_id, date
):
    """Public client methods must reject traversal before touching the filesystem."""
    from importlib import import_module

    module_name, class_name = client_cls_path.rsplit(".", 1)
    client_cls = getattr(import_module(module_name), class_name)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    client = client_cls("test-key")

    with pytest.raises(ValueError):
        client.list_conflicts(agent_id, date)
    with pytest.raises(ValueError):
        client.resolve_conflict(agent_id, date, conflict_index=0, action="keep_both")


@pytest.mark.asyncio
async def test_ui_conflict_scans_use_active_backend(tmp_path, monkeypatch):
    """The UI scan timeline must not mix cloud and on-prem reports."""
    from memanto.app.ui.routes import ui_router

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    onprem_report = (
        tmp_path
        / ".memanto"
        / "on-prem"
        / "conflicts"
        / "agent-1_2026-07-21_conflicts.json"
    )
    _write_conflicts(onprem_report, "on-prem conflict")

    result = await ui_router.list_conflict_scans(agent_id="agent-1", _=None)

    assert result["scans"]["2026-07-21"]["conflict_count"] == 1

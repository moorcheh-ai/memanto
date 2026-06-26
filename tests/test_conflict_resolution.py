from __future__ import annotations

import json
from pathlib import Path

import pytest

import memanto.cli.client.direct_client as direct_client_module
import memanto.cli.client.sdk_client as sdk_client_module
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


class RecordingWriteService:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_memory(self, memory_id: str, namespace: str) -> None:
        self.deleted.append((memory_id, namespace))


class ConflictTestClient(DirectClient):
    def __init__(self) -> None:
        super().__init__(api_key="test-key")
        self.write_service = RecordingWriteService()

    def _get_write_service(self):
        return self.write_service


def _write_conflict_report(home: Path, agent_id: str, date: str) -> Path:
    conflict_dir = home / ".memanto" / "conflicts"
    conflict_dir.mkdir(parents=True)
    report_path = conflict_dir / f"{agent_id}_{date}_conflicts.json"
    report_path.write_text(
        json.dumps(
            [
                {
                    "title": "already resolved",
                    "old_memory_id": "old-0",
                    "new_memory_id": "new-0",
                    "resolved": True,
                },
                {
                    "title": "visible conflict",
                    "old_memory_id": "old-1",
                    "new_memory_id": "new-1",
                    "resolved": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    return report_path


@pytest.mark.parametrize(
    ("client_cls", "client_module"),
    [(DirectClient, direct_client_module), (SdkClient, sdk_client_module)],
)
def test_list_conflicts_preserves_original_conflict_index(
    tmp_path, monkeypatch, client_cls, client_module
):
    agent_id = "agent-a"
    date = "2026-05-08"
    _write_conflict_report(tmp_path, agent_id, date)
    monkeypatch.setattr(client_module.Path, "home", lambda: tmp_path)

    conflicts = client_cls(api_key="test-key").list_conflicts(agent_id=agent_id, date=date)

    assert len(conflicts) == 1
    assert conflicts[0]["title"] == "visible conflict"
    assert conflicts[0]["conflict_index"] == 1


def test_resolve_visible_conflict_uses_original_index(tmp_path, monkeypatch):
    agent_id = "agent-a"
    date = "2026-05-08"
    report_path = _write_conflict_report(tmp_path, agent_id, date)
    monkeypatch.setattr(direct_client_module.Path, "home", lambda: tmp_path)

    client = ConflictTestClient()
    visible = client.list_conflicts(agent_id=agent_id, date=date)

    result = client.resolve_conflict(
        agent_id=agent_id,
        date=date,
        conflict_index=visible[0]["conflict_index"],
        action="keep_new",
    )

    assert result["status"] == "resolved"
    assert result["deleted"] == "old-1"
    assert client.write_service.deleted == [("old-1", "memanto_agent_agent-a")]

    stored_conflicts = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored_conflicts[0].get("resolution") != "keep_new"
    assert stored_conflicts[1]["resolution"] == "keep_new"

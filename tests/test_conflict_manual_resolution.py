import json
from pathlib import Path

import pytest

from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


class FailingStoreService:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_memory(self, memory_id: str, namespace: str) -> bool:
        self.deleted.append((memory_id, namespace))
        return True

    def store_memory(self, memory):
        raise RuntimeError("store failed")


@pytest.mark.parametrize("client_cls", [DirectClient, SdkClient])
def test_manual_conflict_resolution_does_not_delete_on_store_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client_cls
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    conflicts_dir = tmp_path / ".memanto" / "conflicts"
    conflicts_dir.mkdir(parents=True)
    conflict_file = conflicts_dir / "agent-1_2026-07-05_conflicts.json"
    conflict_file.write_text(
        json.dumps(
            [
                {
                    "title": "Conflicting preference",
                    "type": "fact",
                    "old_memory_id": "old-memory",
                    "new_memory_id": "new-memory",
                    "resolved": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    service = FailingStoreService()
    client = client_cls("test-api-key")
    monkeypatch.setattr(client, "_get_write_service", lambda: service)

    with pytest.raises(RuntimeError, match="store failed"):
        client.resolve_conflict(
            agent_id="agent-1",
            date="2026-07-05",
            conflict_index=0,
            action="manual",
            manual_content="Keep the corrected memory.",
        )

    assert service.deleted == []
    persisted_conflicts = json.loads(conflict_file.read_text(encoding="utf-8"))
    assert persisted_conflicts[0]["resolved"] is False

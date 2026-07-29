"""Regression tests for conflict-resolution cleanup failures."""

import json
from unittest.mock import MagicMock

import pytest


def _write_conflict_report(tmp_path, agent_id, date):
    """Create a production-shaped conflict report for resolution tests."""
    conflicts_dir = tmp_path / ".memanto" / "conflicts"
    conflicts_dir.mkdir(parents=True)
    report_path = conflicts_dir / f"{agent_id}_{date}_conflicts.json"
    report_path.write_text(
        json.dumps(
            [
                {
                    "type": "conflict",
                    "title": "Deployment region mismatch",
                    "old_memory_id": "old-memory",
                    "new_memory_id": "new-memory",
                    "old_content": "Deploy to us-east-1",
                    "new_content": "Deploy to eu-west-1",
                    "resolved": False,
                    "resolution": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    return report_path


@pytest.mark.parametrize(
    ("module_path", "class_name"),
    [
        ("memanto.cli.client.direct_client", "DirectClient"),
        ("memanto.cli.client.sdk_client", "SdkClient"),
    ],
)
def test_conflict_stays_unresolved_when_required_delete_fails(
    module_path, class_name, tmp_path, monkeypatch
):
    """Keep the persisted conflict unresolved when deletion raises."""
    client_module = pytest.importorskip(module_path)
    client_class = getattr(client_module, class_name)
    monkeypatch.setattr(
        client_module.Path,
        "home",
        classmethod(lambda cls: tmp_path),
    )

    agent_id = "test-agent"
    date = "2026-05-08"
    report_path = _write_conflict_report(tmp_path, agent_id, date)

    write_service = MagicMock()
    write_service.delete_memory.side_effect = RuntimeError("backend unavailable")

    client = client_class(api_key="test-key")
    client._get_write_service = lambda: write_service

    with pytest.raises(ValueError, match="required memory deletion failed"):
        client.resolve_conflict(
            agent_id=agent_id,
            date=date,
            conflict_index=0,
            action="keep_old",
        )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted[0]["resolved"] is False
    assert persisted[0]["resolution"] is None
    write_service.delete_memory.assert_called_once()


@pytest.mark.parametrize(
    ("module_path", "class_name"),
    [
        ("memanto.cli.client.direct_client", "DirectClient"),
        ("memanto.cli.client.sdk_client", "SdkClient"),
    ],
)
def test_conflict_stays_unresolved_when_required_delete_returns_false(
    module_path, class_name, tmp_path, monkeypatch
):
    """Keep the persisted conflict unresolved when deletion returns false."""
    client_module = pytest.importorskip(module_path)
    client_class = getattr(client_module, class_name)
    monkeypatch.setattr(
        client_module.Path,
        "home",
        classmethod(lambda cls: tmp_path),
    )

    agent_id = "test-agent"
    date = "2026-05-08"
    report_path = _write_conflict_report(tmp_path, agent_id, date)

    write_service = MagicMock()
    write_service.delete_memory.return_value = False

    client = client_class(api_key="test-key")
    client._get_write_service = lambda: write_service

    with pytest.raises(ValueError, match="required memory deletion failed"):
        client.resolve_conflict(
            agent_id=agent_id,
            date=date,
            conflict_index=0,
            action="keep_old",
        )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted[0]["resolved"] is False
    assert persisted[0]["resolution"] is None
    write_service.delete_memory.assert_called_once()


@pytest.mark.parametrize(
    ("module_path", "class_name"),
    [
        ("memanto.cli.client.direct_client", "DirectClient"),
        ("memanto.cli.client.sdk_client", "SdkClient"),
    ],
)
@pytest.mark.parametrize("delete_result", [RuntimeError("backend unavailable"), False])
def test_manual_conflict_resolution_does_not_mark_resolved_after_delete_failure(
    module_path, class_name, delete_result, tmp_path, monkeypatch
):
    """Store replacement first, but do not mark resolved if deletions fail."""
    client_module = pytest.importorskip(module_path)
    client_class = getattr(client_module, class_name)
    monkeypatch.setattr(
        client_module.Path,
        "home",
        classmethod(lambda cls: tmp_path),
    )

    agent_id = "test-agent"
    date = "2026-05-08"
    report_path = _write_conflict_report(tmp_path, agent_id, date)

    write_service = MagicMock()
    if isinstance(delete_result, Exception):
        write_service.delete_memory.side_effect = delete_result
    else:
        write_service.delete_memory.return_value = delete_result

    client = client_class(api_key="test-key")
    client._get_write_service = lambda: write_service

    with pytest.raises(ValueError, match="required memory deletion failed"):
        client.resolve_conflict(
            agent_id=agent_id,
            date=date,
            conflict_index=0,
            action="manual",
            manual_content="Deploy to us-east-1 unless failover is active",
        )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted[0]["resolved"] is False
    assert persisted[0]["resolution"] is None
    write_service.store_memory.assert_called_once()

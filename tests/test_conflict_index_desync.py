"""Regression tests for conflict-resolution index handling.

Background — the bug these guard against
----------------------------------------
``DirectClient.list_conflicts`` returns only *unresolved* conflicts, while
``resolve_conflict`` addresses a conflict by its index into the *full* report.
Previously ``list_conflicts`` exposed no stable identifier, so the REST API and
Web UI resolved conflicts by the position of the item within the filtered list.
The two index spaces agree only until the first resolution; afterwards they
desync, and because resolution deletes memories, the caller deleted a memory it
never selected while the conflict it did select stayed unresolved.

The fix:
  * ``list_conflicts`` now tags each returned conflict with its stable ``index``
    into the full report.
  * ``resolve_conflict`` refuses to act on an already-resolved index (defense in
    depth against a stale/desynced index).

These tests pin both behaviours.
"""

import json
from unittest.mock import MagicMock

import pytest

from memanto.cli.client import direct_client as direct_client_module
from memanto.cli.client.direct_client import DirectClient


def _conflict(letter: str) -> dict:
    """A conflict whose old/new memory ids are tagged with its letter so we can
    see exactly which memory a resolution deleted."""
    return {
        "type": "contradiction",
        "title": f"Conflict {letter}",
        "old_memory_id": f"{letter}_old",
        "old_content": f"old {letter}",
        "new_memory_id": f"{letter}_new",
        "new_content": f"new {letter}",
        "description": f"conflict {letter}",
        "recommendation": "keep_new",
        "resolved": False,
        "resolution": None,
    }


def _write_report(tmp_path, agent_id: str, date: str, conflicts: list[dict]) -> None:
    path = tmp_path / ".memanto" / "conflicts" / f"{agent_id}_{date}_conflicts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(conflicts), encoding="utf-8")


def _make_client(tmp_path, monkeypatch):
    """A DirectClient whose home dir is redirected and whose write service is a
    mock recording every delete_memory call."""
    monkeypatch.setattr(
        direct_client_module.Path, "home", classmethod(lambda cls: tmp_path)
    )
    client = DirectClient(api_key="test-key")
    mock_write = MagicMock()
    mock_write.delete_memory.return_value = True
    mock_write.store_memory.return_value = {"id": "manual_new"}
    client._write_service = mock_write  # inject; _get_write_service returns this
    return client, mock_write


def _deleted_ids(mock_write) -> list[str]:
    return [call.args[0] for call in mock_write.delete_memory.call_args_list]


def test_list_conflicts_exposes_stable_full_report_index(tmp_path, monkeypatch):
    """Each unresolved conflict must carry its index into the full report, and
    that index must stay stable after an earlier conflict is resolved."""
    agent_id, date = "agent-1", "2026-07-01"
    _write_report(
        tmp_path, agent_id, date, [_conflict("A"), _conflict("B"), _conflict("C")]
    )
    client, _ = _make_client(tmp_path, monkeypatch)

    listed = client.list_conflicts(agent_id=agent_id, date=date)
    assert [(c["title"], c["index"]) for c in listed] == [
        ("Conflict A", 0),
        ("Conflict B", 1),
        ("Conflict C", 2),
    ]

    # Resolve A. B and C must keep their ORIGINAL indices (1 and 2), not
    # renumber to 0 and 1.
    client.resolve_conflict(agent_id, date, conflict_index=0, action="keep_new")
    listed_after = client.list_conflicts(agent_id=agent_id, date=date)
    assert [(c["title"], c["index"]) for c in listed_after] == [
        ("Conflict B", 1),
        ("Conflict C", 2),
    ]


def test_resolving_by_provided_index_deletes_the_correct_memory(tmp_path, monkeypatch):
    """A caller that resolves using the ``index`` from list_conflicts deletes
    exactly the memory it selected, even after an earlier resolution."""
    agent_id, date = "agent-1", "2026-07-01"
    _write_report(
        tmp_path, agent_id, date, [_conflict("A"), _conflict("B"), _conflict("C")]
    )
    client, mock_write = _make_client(tmp_path, monkeypatch)

    # Resolve A first (keep_new deletes A_old).
    a = next(
        c
        for c in client.list_conflicts(agent_id=agent_id, date=date)
        if c["title"] == "Conflict A"
    )
    client.resolve_conflict(
        agent_id, date, conflict_index=a["index"], action="keep_new"
    )
    assert _deleted_ids(mock_write) == ["A_old"]

    # Now select conflict C from the freshly listed (filtered) conflicts and
    # resolve it by its provided index — NOT by its position in the list.
    remaining = client.list_conflicts(agent_id=agent_id, date=date)
    c = next(x for x in remaining if x["title"] == "Conflict C")
    # C is at filtered position 1 but its stable index is 2; the fix means we
    # pass 2 and delete C_old, not B_old.
    client.resolve_conflict(
        agent_id, date, conflict_index=c["index"], action="keep_new"
    )

    assert _deleted_ids(mock_write)[1:] == ["C_old"], (
        f"expected C_old to be deleted, got {_deleted_ids(mock_write)[1:]}"
    )

    report = json.loads(
        (
            tmp_path / ".memanto" / "conflicts" / f"{agent_id}_{date}_conflicts.json"
        ).read_text(encoding="utf-8")
    )
    by_title = {c["title"]: c for c in report}
    assert by_title["Conflict C"]["resolved"] is True
    assert by_title["Conflict B"]["resolved"] is False


def test_resolving_an_already_resolved_index_is_rejected(tmp_path, monkeypatch):
    """Defense in depth: acting on an already-resolved index must raise rather
    than silently re-delete a memory."""
    agent_id, date = "agent-1", "2026-07-01"
    _write_report(tmp_path, agent_id, date, [_conflict("A"), _conflict("B")])
    client, mock_write = _make_client(tmp_path, monkeypatch)

    client.resolve_conflict(agent_id, date, conflict_index=0, action="keep_new")
    assert _deleted_ids(mock_write) == ["A_old"]

    with pytest.raises(ValueError, match="already resolved"):
        client.resolve_conflict(agent_id, date, conflict_index=0, action="keep_new")

    # No second deletion happened.
    assert _deleted_ids(mock_write) == ["A_old"]

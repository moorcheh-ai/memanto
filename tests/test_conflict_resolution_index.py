"""Conflict resolution must act on the conflict the caller reviewed.

The conflict report (``~/.memanto/conflicts/{agent}_{date}_conflicts.json``) is
addressed by position in the FULL list, while ``list_conflicts()`` returns only
the UNRESOLVED entries. Numbering the filtered list therefore addresses a
different conflict as soon as one earlier conflict has been resolved — and
resolution hard-deletes memories, so the mistake is not recoverable.

These tests pin both halves of the contract:

* ``list_conflicts()`` must hand back the authoritative ``conflict_index``.
* ``resolve_conflict()`` must fail closed — before deleting anything — when the
  addressed conflict was already resolved or does not match the memory ids the
  caller reviewed.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient

AGENT = "conflict-agent"
DATE = "2026-07-30"

# index 0 was resolved earlier with keep_new, so mem-new-0 is the memory the
# user deliberately kept. Indices 1 and 2 are still open.
REPORT = [
    {
        "type": "contradiction",
        "title": "Timezone",
        "old_memory_id": "mem-old-0",
        "new_memory_id": "mem-new-0",
        "resolved": True,
        "resolution": "keep_new",
    },
    {
        "type": "contradiction",
        "title": "Favourite editor",
        "old_memory_id": "mem-old-1",
        "new_memory_id": "mem-new-1",
        "resolved": False,
    },
    {
        "type": "update",
        "title": "Deploy target",
        "old_memory_id": "mem-old-2",
        "new_memory_id": "mem-new-2",
        "resolved": False,
    },
]

DESTRUCTIVE_ACTIONS = ["keep_old", "keep_new", "remove_both", "manual"]


def _write_report(home: Path, conflicts, agent=AGENT, date=DATE) -> Path:
    """Write a conflict report into a fake HOME and return its path."""
    path = home / ".memanto" / "conflicts" / f"{agent}_{date}_conflicts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(conflicts, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point Path.home() and $HOME at an isolated directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.fixture
def report(fake_home):
    """A report whose first conflict is already resolved."""
    return _write_report(fake_home, REPORT)


class _Recorder:
    """Records the write-service calls a resolution performs."""

    def __init__(self):
        self.deleted: list[str] = []
        self.stored: list[object] = []

    def service(self):
        svc = MagicMock()

        def _delete(memory_id, namespace):
            self.deleted.append(memory_id)
            return True

        def _store(memory, context=None):
            self.stored.append(memory)
            return {"id": "mem-manual"}

        svc.delete_memory.side_effect = _delete
        svc.store_memory.side_effect = _store
        return svc


@pytest.fixture
def recorder():
    return _Recorder()


def _client(cls, recorder):
    """Build a CLI client whose writes are recorded instead of performed."""
    client = cls("test-key")
    client._get_write_service = recorder.service  # type: ignore[method-assign]
    return client


CLIENT_CLASSES = [DirectClient, SdkClient]


# ---------------------------------------------------------------------------
# list_conflicts: the index has to travel with the data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_list_conflicts_reports_index_in_full_report(cls, report, recorder):
    """Each unresolved conflict carries its position in the full report."""
    conflicts = _client(cls, recorder).list_conflicts(AGENT, DATE)

    assert [c["title"] for c in conflicts] == ["Favourite editor", "Deploy target"]
    # Positions in the response are 0 and 1; report indices are 1 and 2.
    assert [c["conflict_index"] for c in conflicts] == [1, 2]


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_list_conflicts_index_matches_stored_memory_ids(cls, report, recorder):
    """conflict_index must address the same entry in the report on disk."""
    conflicts = _client(cls, recorder).list_conflicts(AGENT, DATE)
    on_disk = json.loads(report.read_text())

    for conflict in conflicts:
        stored = on_disk[conflict["conflict_index"]]
        assert stored["old_memory_id"] == conflict["old_memory_id"]
        assert stored["new_memory_id"] == conflict["new_memory_id"]


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_list_conflicts_overrides_index_from_file(cls, fake_home, recorder):
    """A stray conflict_index in the report cannot redirect a resolve.

    The report is generated from LLM output, so the field is not trustworthy
    input — position in the file is the only authority.
    """
    _write_report(
        fake_home,
        [
            dict(REPORT[0]),
            {**REPORT[1], "conflict_index": 99},
            dict(REPORT[2]),
        ],
    )

    conflicts = _client(cls, recorder).list_conflicts(AGENT, DATE)
    assert [c["conflict_index"] for c in conflicts] == [1, 2]


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_list_conflicts_does_not_mutate_report(cls, report, recorder):
    """Listing is read-only: the added field must not reach the file."""
    before = report.read_text()
    _client(cls, recorder).list_conflicts(AGENT, DATE)
    assert report.read_text() == before
    assert all("conflict_index" not in c for c in json.loads(report.read_text()))


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_list_conflicts_indices_are_stable_across_resolutions(cls, report, recorder):
    """Resolving one conflict must not renumber the remaining ones."""
    client = _client(cls, recorder)
    first = client.list_conflicts(AGENT, DATE)
    client.resolve_conflict(AGENT, DATE, first[0]["conflict_index"], "keep_new")

    remaining = client.list_conflicts(AGENT, DATE)
    assert [c["conflict_index"] for c in remaining] == [2]
    assert remaining[0]["title"] == "Deploy target"


# ---------------------------------------------------------------------------
# resolve_conflict: fail closed before deleting anything
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
@pytest.mark.parametrize("action", DESTRUCTIVE_ACTIONS)
def test_resolve_rejects_already_resolved_conflict(cls, action, report, recorder):
    """Re-resolving a settled conflict would destroy the memory it kept."""
    with pytest.raises(ValueError, match="already resolved"):
        _client(cls, recorder).resolve_conflict(
            AGENT,
            DATE,
            0,
            action,
            manual_content="replacement" if action == "manual" else None,
        )

    assert recorder.deleted == []
    assert recorder.stored == []
    # The earlier resolution is left exactly as it was.
    assert json.loads(report.read_text())[0]["resolution"] == "keep_new"


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
@pytest.mark.parametrize("action", DESTRUCTIVE_ACTIONS)
def test_resolve_rejects_memory_id_mismatch(cls, action, report, recorder):
    """An index that no longer points at the reviewed conflict is refused."""
    with pytest.raises(ValueError, match="does not match the reviewed conflict"):
        _client(cls, recorder).resolve_conflict(
            AGENT,
            DATE,
            2,
            action,
            manual_content="replacement" if action == "manual" else None,
            expected_old_memory_id="mem-old-1",
            expected_new_memory_id="mem-new-1",
        )

    assert recorder.deleted == []
    assert recorder.stored == []
    assert json.loads(report.read_text())[2].get("resolved") is False


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_resolve_rejects_new_memory_id_mismatch_alone(cls, report, recorder):
    """Either side of the pair is enough to detect drift."""
    with pytest.raises(ValueError, match="new_memory_id"):
        _client(cls, recorder).resolve_conflict(
            AGENT,
            DATE,
            2,
            "remove_both",
            expected_new_memory_id="mem-new-1",
        )

    assert recorder.deleted == []


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_resolve_survives_report_regenerated_between_list_and_resolve(
    cls, report, recorder, fake_home
):
    """Realistic race: 'Detect Conflicts Now' rewrites the report mid-review.

    The stale index still exists, so without the guard the resolution would
    silently delete a pair the caller never saw.
    """
    client = _client(cls, recorder)
    reviewed = client.list_conflicts(AGENT, DATE)[0]

    # Report regenerated: same length, entirely different conflicts.
    _write_report(
        fake_home,
        [
            {
                "type": "contradiction",
                "title": "Something else",
                "old_memory_id": f"other-old-{i}",
                "new_memory_id": f"other-new-{i}",
                "resolved": False,
            }
            for i in range(3)
        ],
    )

    with pytest.raises(ValueError, match="does not match the reviewed conflict"):
        client.resolve_conflict(
            AGENT,
            DATE,
            reviewed["conflict_index"],
            "remove_both",
            expected_old_memory_id=reviewed["old_memory_id"],
            expected_new_memory_id=reviewed["new_memory_id"],
        )

    assert recorder.deleted == []


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_resolve_accepts_matching_expected_ids(cls, report, recorder):
    """The guard must not get in the way of a correct resolution."""
    client = _client(cls, recorder)
    reviewed = client.list_conflicts(AGENT, DATE)[0]

    result = client.resolve_conflict(
        AGENT,
        DATE,
        reviewed["conflict_index"],
        "remove_both",
        expected_old_memory_id=reviewed["old_memory_id"],
        expected_new_memory_id=reviewed["new_memory_id"],
    )

    assert result["status"] == "resolved"
    assert recorder.deleted == ["mem-old-1", "mem-new-1"]
    assert json.loads(report.read_text())[1]["resolved"] is True


@pytest.mark.parametrize("cls", CLIENT_CLASSES)
def test_resolve_manual_does_not_store_replacement_on_mismatch(cls, report, recorder):
    """A refused manual resolution must not leave an orphan memory behind."""
    with pytest.raises(ValueError):
        _client(cls, recorder).resolve_conflict(
            AGENT,
            DATE,
            2,
            "manual",
            manual_content="merged value",
            expected_old_memory_id="mem-old-1",
        )

    assert recorder.stored == []
    assert recorder.deleted == []


# ---------------------------------------------------------------------------
# Web UI: the flow that actually shipped
# ---------------------------------------------------------------------------


def _ui_client():
    from memanto.app.ui.routes.ui_router import router as ui_router

    app = FastAPI()
    app.include_router(ui_router)
    # _require_local only accepts loopback callers.
    return TestClient(app, client=("127.0.0.1", 45678))


def _ui_patches(recorder):
    return (
        patch(
            "memanto.app.ui.routes.ui_router._config_manager.get_api_key",
            return_value="test-key",
        ),
        patch(
            "memanto.cli.client.direct_client.DirectClient._get_write_service",
            side_effect=recorder.service,
        ),
    )


def test_ui_resolves_the_conflict_shown_on_the_card(report, recorder):
    """End-to-end: acting on the first card must touch only that conflict.

    Before the fix the UI sent the card's array position, so clicking the first
    card deleted the memories of report index 0 — including the memory a
    previous ``keep_new`` decision had preserved — while the reviewed conflict
    stayed unresolved and came back on the next reload.
    """
    api = _ui_client()
    get_key, get_write = _ui_patches(recorder)

    with get_key, get_write:
        listed = api.get(f"/api/ui/conflicts?agent_id={AGENT}&date={DATE}").json()
        cards = listed["conflicts"]
        assert listed["count"] == 2

        # Exactly what the frontend does for the first card.
        card = cards[0]
        idx = card["conflict_index"]
        resp = api.post(
            "/api/ui/conflicts/resolve",
            json={
                "agent_id": AGENT,
                "date": DATE,
                "conflict_index": idx,
                "action": "remove_both",
                "expected_old_memory_id": card["old_memory_id"],
                "expected_new_memory_id": card["new_memory_id"],
            },
        )

    assert resp.status_code == 200
    assert recorder.deleted == [card["old_memory_id"], card["new_memory_id"]]
    # The memory kept by the earlier decision is untouched.
    assert "mem-new-0" not in recorder.deleted

    after = json.loads(report.read_text())
    assert after[1]["resolved"] is True
    assert after[1]["resolution"] == "remove_both"
    assert after[2].get("resolved") is False


def test_ui_rejects_position_based_index_from_a_stale_page(report, recorder):
    """A stale tab that posts the card position is refused, not obeyed."""
    api = _ui_client()
    get_key, get_write = _ui_patches(recorder)

    with get_key, get_write:
        cards = api.get(f"/api/ui/conflicts?agent_id={AGENT}&date={DATE}").json()[
            "conflicts"
        ]
        card = cards[0]
        resp = api.post(
            "/api/ui/conflicts/resolve",
            json={
                "agent_id": AGENT,
                "date": DATE,
                "conflict_index": 0,  # legacy behaviour: array position
                "action": "remove_both",
                "expected_old_memory_id": card["old_memory_id"],
                "expected_new_memory_id": card["new_memory_id"],
            },
        )

    assert resp.status_code == 400
    assert "already resolved" in resp.json()["detail"]
    assert recorder.deleted == []


def test_ui_list_exposes_conflict_index_to_the_frontend(report, recorder):
    """The frontend cannot address the report unless the API exposes the index."""
    api = _ui_client()
    get_key, get_write = _ui_patches(recorder)

    with get_key, get_write:
        cards = api.get(f"/api/ui/conflicts?agent_id={AGENT}&date={DATE}").json()[
            "conflicts"
        ]

    assert [c["conflict_index"] for c in cards] == [1, 2]


def test_shipped_ui_asset_does_not_number_cards_by_position():
    """Guard the one file that has no JS test harness in CI.

    ``index.html`` is served as-is, so a future edit that goes back to using
    the card's array position as ``conflict_index`` would silently restore the
    wrong-memory deletion. Pin the two markers of the fixed behaviour.
    """
    asset = (
        Path(__file__).resolve().parents[1]
        / "memanto"
        / "app"
        / "ui"
        / "static"
        / "index.html"
    )
    source = asset.read_text(encoding="utf-8")

    assert "Number.isInteger(c.conflict_index)" in source, (
        "conflict cards must take the index from the API response"
    )
    assert "resolveConflict(i, rawAgentId" not in source, (
        "conflict cards must not resolve by their position in the response"
    )
    assert "expected_old_memory_id" in source and "expected_new_memory_id" in source, (
        "the UI must send the reviewed memory ids as a guard"
    )


# ---------------------------------------------------------------------------
# HTTP API surface
# ---------------------------------------------------------------------------


def test_resolve_request_model_accepts_expected_memory_ids():
    from memanto.app.models import ConflictResolveRequest

    request = ConflictResolveRequest(
        conflict_index=3,
        action="keep_new",
        expected_old_memory_id="mem-old-1",
        expected_new_memory_id="mem-new-1",
    )
    assert request.expected_old_memory_id == "mem-old-1"
    assert request.expected_new_memory_id == "mem-new-1"


def test_resolve_request_model_defaults_guards_to_none():
    from memanto.app.models import ConflictResolveRequest

    request = ConflictResolveRequest(conflict_index=0, action="keep_both")
    assert request.expected_old_memory_id is None
    assert request.expected_new_memory_id is None


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------


def test_cli_interactive_resolve_uses_report_index_and_guards(report, recorder):
    """`memanto conflicts` must resolve the conflict it displayed."""
    from typer.testing import CliRunner

    from memanto.cli.main import app

    client = MagicMock()
    client.list_conflicts.return_value = [
        {**REPORT[1], "conflict_index": 1},
        {**REPORT[2], "conflict_index": 2},
    ]
    client.resolve_conflict.return_value = {"status": "resolved"}

    with (
        patch("memanto.cli.commands.memory.get_client", return_value=client),
        patch("memanto.cli.commands.memory.config_manager") as cfg,
    ):
        cfg.get_active_session.return_value = (AGENT, "token")
        # Choose "keep_new" on the first displayed conflict, then quit.
        result = CliRunner().invoke(app, ["conflicts", "--date", DATE], input="2\nq\n")

    assert result.exit_code == 0, result.output
    client.resolve_conflict.assert_called_once()
    kwargs = client.resolve_conflict.call_args.kwargs
    assert kwargs["conflict_index"] == 1
    assert kwargs["action"] == "keep_new"
    assert kwargs["expected_old_memory_id"] == "mem-old-1"
    assert kwargs["expected_new_memory_id"] == "mem-new-1"

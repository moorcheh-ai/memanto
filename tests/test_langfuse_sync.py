"""Tests for the shared Langfuse sync path (CLI + UI tile).

``run_langfuse_sync`` is what makes re-running safe: it reconciles mapped rows
against the ledger instead of writing them all, so both ``memanto migrate
langfuse`` and the UI's migrate tile stay idempotent.
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memanto.cli.migrate.langfuse_config import project_key
from memanto.cli.migrate.langfuse_rules import CaptureConfig
from memanto.cli.migrate.langfuse_state import load_state, scope_key, state_path
from memanto.cli.migrate.runner import run_langfuse_sync


def observation(i=0, message="RateLimitError: quota exceeded", name="summarize_node"):
    return {
        "id": f"obs-{i}",
        "traceId": f"trace-{i}",
        "projectId": "proj-1",
        "name": name,
        "level": "ERROR",
        "statusMessage": message,
        "startTime": f"2026-08-01T12:{i % 60:02d}:00Z",
        "endTime": f"2026-08-01T12:{i % 60:02d}:01Z",
    }


def export(observations=None):
    return {
        "api_base": "https://cloud.langfuse.com",
        "summary": {"capture_modes": ["errors"], "score_threshold": 0.5},
        "observations": observations
        if observations is not None
        else [observation(i) for i in range(20)],
        "scores": [],
    }


@pytest.fixture
def client():
    """A batch_remember/update_memory double that hands back unique ids."""
    ids = itertools.count(1)
    fake = MagicMock()
    fake.batch_remember.side_effect = lambda agent_id, memories: {
        "successful": len(memories),
        "failed": 0,
        "results": [{"id": f"mem-{next(ids)}", "status": "queued"} for _ in memories],
    }
    fake.update_memory.return_value = {"status": "updated"}
    return fake


ERRORS_ONLY = CaptureConfig(modes=frozenset({"errors"}))


def sync(client, state, exp=None, dry_run=False, config=ERRORS_ONLY):
    return run_langfuse_sync(
        export=exp or export(),
        client=client,
        agent_id="test-agent",
        state=state,
        dry_run=dry_run,
        config=config,
    )


# --------------------------------------------------------------------------
# Grouping and the write path
# --------------------------------------------------------------------------


def test_sync_groups_observations_before_writing(client):
    summary, rows, _ = sync(client, {})

    assert summary.observation_count == 20
    assert summary.signature_count == 1  # 20 occurrences, one signature
    assert len(rows) == 1
    assert summary.imported == 1
    assert summary.type_counts == {"error": 1}


def test_dry_run_writes_nothing(client):
    summary, rows, plan = sync(client, {}, dry_run=True)

    client.batch_remember.assert_not_called()
    client.update_memory.assert_not_called()
    assert summary.new == 1 and summary.imported == 0
    assert len(plan.new_rows) == 1


def test_second_sync_is_a_no_op(client):
    """Re-running must not duplicate — the whole reason the ledger exists."""
    state: dict = {}
    sync(client, state)
    summary, _, _ = sync(client, state)

    assert client.batch_remember.call_count == 1
    assert (summary.new, summary.imported, summary.unchanged) == (0, 0, 1)


def test_recurring_signature_updates_in_place(client):
    state: dict = {}
    sync(client, state, export([observation(i) for i in range(5)]))

    summary, _, _ = sync(client, state, export([observation(i) for i in range(40)]))

    assert client.batch_remember.call_count == 1  # no second write
    assert summary.changed == 1
    assert summary.updated == 1
    client.update_memory.assert_called_once()
    assert client.update_memory.call_args.kwargs["memory_id"] == "mem-1"


def test_a_genuinely_new_signature_is_written_on_a_later_sync(client):
    state: dict = {}
    sync(client, state, export([observation(i) for i in range(20)]))

    summary, _, _ = sync(
        client,
        state,
        export(
            [observation(i) for i in range(20)]
            + [observation(99, message="TimeoutError: no response")]
        ),
    )

    assert summary.new == 1  # the TimeoutError
    assert summary.unchanged == 1  # the RateLimitError, identical to last time


def test_memory_reflects_the_latest_sync_window(client):
    """Counts describe the window that was pulled, not a running total.

    A narrower window legitimately reports fewer occurrences, so the memory
    updates rather than being left stale. The content always names the time
    range it is describing, so it never overstates.
    """
    state: dict = {}
    sync(client, state, export([observation(i) for i in range(20)]))

    summary, rows, _ = sync(client, state, export([observation(0)]))

    assert summary.changed == 1
    assert rows[0]["occurrences"] == 1


def test_batches_are_chunked_at_one_hundred(client):
    observations = [
        observation(i, message=f"Error{i}Error: distinct fault") for i in range(250)
    ]
    summary, rows, _ = sync(client, {}, export(observations))

    assert len(rows) == 250
    assert summary.batches == 3
    assert client.batch_remember.call_count == 3
    assert all(
        len(call.kwargs["memories"]) <= 100
        for call in client.batch_remember.call_args_list
    )


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


def test_a_failing_batch_is_counted_and_retried_next_sync(client):
    client.batch_remember.side_effect = RuntimeError("moorcheh is down")
    state: dict = {}

    summary, _, _ = sync(client, state, export([observation(0)]))
    assert summary.failed == 1
    assert "moorcheh is down" in summary.errors[0]
    assert state.get("signatures", {}) == {}


def test_a_failing_update_does_not_settle_the_ledger(client):
    state: dict = {}
    sync(client, state, export([observation(0)]))
    client.update_memory.side_effect = RuntimeError("nope")

    summary, _, _ = sync(client, state, export([observation(i) for i in range(30)]))

    assert summary.failed == 1
    assert summary.updated == 0
    # Still pending, so the next sync tries again.
    assert sync(client, state, export([observation(i) for i in range(30)]))[0].changed


# --------------------------------------------------------------------------
# UI tile — same path, over HTTP
# --------------------------------------------------------------------------


def _ui_app():
    from memanto.app.ui.routes.ui_router import _require_local, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_local] = lambda: None
    return app


@pytest.fixture
def ui(tmp_path, monkeypatch, client):
    from memanto.app.ui.routes import ui_router as mod

    monkeypatch.setattr(mod, "_build_ui_direct_client", lambda: client)
    monkeypatch.setattr(mod._config_manager, "get_migrate_dir", lambda p: tmp_path)
    monkeypatch.setattr(
        mod._config_manager, "get_active_session", lambda: ("test-agent", "tok")
    )
    return TestClient(_ui_app())


@pytest.fixture
def export_file(tmp_path):
    import json

    path = tmp_path / "langfuse_export.json"
    path.write_text(json.dumps(export()), encoding="utf-8")
    return str(path)


def body(export_file, **extra):
    return {
        "provider": "langfuse",
        "file": export_file,
        "agent_id": "test-agent",
        "capture": ["errors"],
        **extra,
    }


def test_ui_dry_run_reports_the_reconciliation_plan(ui, export_file):
    res = ui.post("/api/ui/migrate/dry-run", json=body(export_file)).json()

    assert res["source_count"] == 20
    assert res["mapped_count"] == 1
    assert res["plan"] == {"new": 1, "changed": 0, "unchanged": 0}
    # Langfuse is not a memory store to benchmark against — no savings tiles.
    assert res["savings"] == {}


def test_ui_tile_clicked_twice_does_not_duplicate(ui, export_file, client, tmp_path):
    first = ui.post("/api/ui/migrate/import", json=body(export_file)).json()["summary"]
    second = ui.post("/api/ui/migrate/import", json=body(export_file)).json()["summary"]

    assert (first["new"], first["imported"]) == (1, 1)
    assert (second["new"], second["imported"], second["unchanged"]) == (0, 0, 1)
    assert client.batch_remember.call_count == 1
    # The ledger was persisted under this project+agent scope, which is what
    # survives a server restart.
    scope = scope_key(project_key(api_key=None), "test-agent")
    assert load_state(state_path(tmp_path), scope)["signatures"]


def test_ui_rejects_an_unknown_capture_mode(ui, export_file):
    res = ui.post("/api/ui/migrate/dry-run", json=body(export_file, capture=["nope"]))

    assert res.status_code == 400
    assert "Unknown capture mode" in res.json()["detail"]


def test_ui_rejects_a_half_credential(ui):
    res = ui.post(
        "/api/ui/migrate/dry-run",
        json={"provider": "langfuse", "api_key": "pk-lf-only"},
    )

    assert res.status_code == 400
    assert "both keys" in res.json()["detail"]


def test_langfuse_is_an_accepted_ui_provider():
    from memanto.app.ui.routes.ui_router import _MIGRATE_PROVIDERS

    assert "langfuse" in _MIGRATE_PROVIDERS


# --------------------------------------------------------------------------
# Capture settings must win over whatever the export file recorded
# --------------------------------------------------------------------------


def _slow_export():
    """An export of non-errored but slow observations, pulled as errors-only."""
    slow = [
        {
            "id": f"s{i}",
            "traceId": f"ts{i}",
            "name": "retrieve_node",
            "level": "DEFAULT",
            "startTime": "2026-08-01T12:00:00Z",
            "endTime": "2026-08-01T12:00:45Z",
        }
        for i in range(4)
    ]
    return {
        "api_base": "https://cloud.langfuse.com",
        # The saved file says errors-only...
        "summary": {"capture_modes": ["errors"], "score_threshold": 0.5},
        "observations": slow,
        "scores": [],
    }


def test_replaying_a_file_honours_the_requested_capture_modes(client):
    """A --file replay must use the caller's settings, not the file's summary."""
    without = sync(client, {}, _slow_export(), dry_run=True)[0]
    assert without.signature_count == 0  # errors-only sees nothing here

    with_slow, rows, _ = sync(
        client,
        {},
        _slow_export(),
        dry_run=True,
        config=CaptureConfig(modes=frozenset({"slow"}), latency_ms=30_000),
    )

    assert with_slow.signature_count == 1
    assert rows[0]["type"] == "observation"


def test_ui_capture_checkboxes_apply_to_file_replays(ui, tmp_path):
    import json

    path = tmp_path / "slow_export.json"
    path.write_text(json.dumps(_slow_export()), encoding="utf-8")
    req = {"provider": "langfuse", "file": str(path), "agent_id": "test-agent"}

    errors_only = ui.post(
        "/api/ui/migrate/dry-run", json={**req, "capture": ["errors"]}
    )
    with_slow = ui.post(
        "/api/ui/migrate/dry-run",
        json={**req, "capture": ["slow"], "latency_ms": 30_000},
    )

    assert errors_only.json()["mapped_count"] == 0
    assert with_slow.json()["mapped_count"] == 1

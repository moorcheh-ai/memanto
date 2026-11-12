"""Tests for the UI achievements store (GET/PUT /api/ui/achievements)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memanto.app.ui.routes import ui_router


def _make_app(local: bool):
    app = FastAPI()
    app.include_router(ui_router.router)
    if local:
        app.dependency_overrides[ui_router._require_local] = lambda: None
    return app


def test_achievements_rejected_from_remote():
    client = TestClient(_make_app(local=False), raise_server_exceptions=False)
    assert client.get("/api/ui/achievements").status_code == 403
    assert client.put("/api/ui/achievements", json={}).status_code == 403


def test_achievements_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "achievements.json"
    monkeypatch.setattr(ui_router, "_achievements_path", lambda: path)
    client = TestClient(_make_app(local=True))

    resp = client.get("/api/ui/achievements")
    assert resp.json() == {
        "exists": False,
        "state": {"earned": {}, "seen": {}, "best": {}},
    }

    state = {
        "earned": {"first-agent": "2026-09-25T18:24:03.036Z"},
        "seen": {"agents": True},
        "best": {"agents": 3},
    }
    assert client.put("/api/ui/achievements", json=state).status_code == 200
    assert path.exists()
    assert client.get("/api/ui/achievements").json() == {"exists": True, "state": state}


def test_achievements_rejects_malformed_state(tmp_path, monkeypatch):
    path = tmp_path / "achievements.json"
    monkeypatch.setattr(ui_router, "_achievements_path", lambda: path)
    client = TestClient(_make_app(local=True))

    resp = client.put("/api/ui/achievements", json={"best": {"agents": "lots"}})
    assert resp.status_code == 422
    assert not path.exists()

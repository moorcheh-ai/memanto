"""``memanto serve`` on Memanto Cloud: the same /api/v2 routes, memories on Memanto Cloud.

The editor extensions (VS Code, Obsidian) spawn ``memanto serve`` and call
health, agents, status, activate, recall (and its temporal variants), answer
and remember. These tests drive the real FastAPI app in Cloud mode against a
fake Memanto Cloud API and check both what the caller gets back and what is
sent to Memanto Cloud.
"""

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

import memanto.app.clients.memanto_cloud as cloud_module
import memanto.app.services.session_service as session_module
import memanto.cli.client.hosted_client as hosted_module
from memanto.app.services.session_service import SessionService
from memanto.app.utils.client_identity import UNKNOWN_CLIENT
from memanto.cli.client.hosted_client import HostedClient

BASE = "https://api.test"
AGENT = "test-agent"

CARD = "[PREFERENCE] Dark mode\n\nThe user prefers dark mode\n\nTags: ui"
CLOUD_MEMORY = {
    "id": "m1",
    "agent_id": AGENT,
    "type": "preference",
    "title": "Dark mode",
    "content": CARD,
    "text": CARD,
    "tags": ["ui"],
    "confidence": 0.9,
    "status": "active",
    "provenance": "explicit_statement",
    "source": "cursor",
    "score": 0.42,
    "created_at": "2026-11-20T04:25:48+00:00",
}


class FakeCloud:
    """Canned Memanto Cloud responses keyed by ``(method, path)``; records requests."""

    def __init__(self) -> None:
        agent = {
            "agent_id": AGENT,
            "pattern": "tool",
            "description": "Coding memory",
            "created_at": "2026-11-20T04:00:00.000Z",
            "status": "ready",
            "memory_count": 3,
        }
        self.routes: dict[tuple[str, str], Any] = {
            ("GET", "/me"): {"user_id": "u1", "plan": "pro"},
            ("GET", "/agents"): {"agents": [agent], "count": 1, "warnings": []},
            ("GET", f"/agents/{AGENT}"): agent,
            ("POST", "/agents"): agent,
            ("POST", f"/agents/{AGENT}/remember"): {
                "memory_id": "m2",
                "agent_id": AGENT,
                "status": "queued",
                "confidence": 0.8,
                "provenance": "explicit_statement",
                "type": "fact",
            },
            ("POST", f"/agents/{AGENT}/recall"): {
                "agent_id": AGENT,
                "count": 1,
                "memories": [CLOUD_MEMORY],
            },
            ("POST", f"/agents/{AGENT}/recall/recent"): {
                "agent_id": AGENT,
                "count": 1,
                "memories": [{**CLOUD_MEMORY, "score": None}],
            },
            ("POST", f"/agents/{AGENT}/recall/changed-since"): {
                "agent_id": AGENT,
                "count": 1,
                "memories": [{**CLOUD_MEMORY, "change_type": "created"}],
            },
            ("POST", f"/agents/{AGENT}/answer"): {
                "agent_id": AGENT,
                "question": "Theme?",
                "answer": "Dark mode.",
                "sources": [{"id": "m1", "score": 0.3, "text": CARD}],
            },
            ("DELETE", f"/agents/{AGENT}"): {"message": "deleted"},
        }
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"detail": {"message": "Not found"}})
        if isinstance(route, httpx.Response):
            return route
        return httpx.Response(200, json=route)

    def sent(self, method: str, path: str) -> list[dict[str, Any]]:
        return [
            cast(dict[str, Any], json.loads(r.content)) if r.content else {}
            for r in self.requests
            if r.method == method and r.url.path == path
        ]


class _Loopback:
    """Make TestClient requests come from 127.0.0.1, like the extensions' calls."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] == "http":
            scope = dict(scope, client=("127.0.0.1", 50000))
        await self.app(scope, receive, send)


@pytest.fixture
def cloud() -> FakeCloud:
    return FakeCloud()


@pytest.fixture
def server(
    cloud: FakeCloud, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """The real app, imported with ``MEMANTO_SERVE_CLOUD=1``, against FakeCloud."""
    monkeypatch.setenv(cloud_module.CLOUD_SERVE_ENV, "1")
    # ConfigManager re-reads ~/.memanto/.env on every call; never let a
    # developer's real key decide what the server accepts.
    monkeypatch.setattr(cloud_module, "cloud_api_key", lambda: "mk_test")
    monkeypatch.setattr(hosted_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(hosted_module, "detect_client", lambda: UNKNOWN_CLIENT)
    monkeypatch.setattr(
        session_module,
        "_session_service",
        SessionService(
            secret_key="test-secret-key-for-serve-cloud-tests",
            sessions_dir=tmp_path / "sessions",
        ),
    )
    monkeypatch.setattr(
        cloud_module,
        "_base",
        HostedClient("mk_test", base_url=BASE, transport=httpx.MockTransport(cloud)),
    )

    import memanto.app.main as main_module

    main_module = importlib.reload(main_module)
    try:
        with TestClient(
            _Loopback(main_module.app),
            base_url="http://127.0.0.1:8000",
            raise_server_exceptions=False,
        ) as client:
            yield client
    finally:
        monkeypatch.delenv(cloud_module.CLOUD_SERVE_ENV)
        importlib.reload(main_module)


def _activate(server: TestClient) -> dict[str, str]:
    response = server.post(f"/api/v2/agents/{AGENT}/activate")
    assert response.status_code == 200, response.text
    return {"X-Session-Token": response.json()["session_token"]}


def test_health_reports_memanto_cloud(server: TestClient, cloud: FakeCloud) -> None:
    body = server.get("/health").json()
    assert body["status"] == "healthy"
    assert body["moorcheh_connected"] is True
    assert cloud.sent("GET", "/me") == [{}]


def test_health_unhealthy_when_cloud_rejects_the_key(
    server: TestClient, cloud: FakeCloud
) -> None:
    cloud.routes[("GET", "/me")] = httpx.Response(401, json={"detail": "bad key"})
    assert server.get("/health").json()["status"] == "unhealthy"


def test_list_agents_comes_from_memanto_cloud(server: TestClient) -> None:
    body = server.get("/api/v2/agents").json()
    assert body["count"] == 1
    agent = body["agents"][0]
    assert agent["agent_id"] == AGENT
    assert agent["namespace"] == f"memanto_agent_{AGENT}"
    assert agent["pattern"] == "tool"
    assert agent["memory_count"] == 3


def test_activate_checks_the_agent_on_cloud_and_starts_a_local_session(
    server: TestClient,
) -> None:
    session = server.post(f"/api/v2/agents/{AGENT}/activate").json()
    assert session["agent_id"] == AGENT
    assert session["session_token"]

    status = server.get("/api/v2/status").json()
    assert status["agent_id"] == AGENT


def test_activate_unknown_agent_is_404(server: TestClient) -> None:
    assert server.post("/api/v2/agents/nobody/activate").status_code == 404


def test_remember_goes_to_cloud_in_the_local_response_shape(
    server: TestClient, cloud: FakeCloud
) -> None:
    headers = _activate(server)
    response = server.post(
        f"/api/v2/agents/{AGENT}/remember",
        json={"content": "Deploys go out on Fridays", "type": "fact"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["memory_id"] == "m2"
    assert body["status"] == "queued"
    assert body["namespace"] == f"memanto_agent_{AGENT}"
    assert body["session_id"]

    sent = cloud.sent("POST", f"/agents/{AGENT}/remember")[-1]
    assert sent["content"] == "Deploys go out on Fridays"
    assert sent["type"] == "fact"
    # The server's own working directory is not the caller's project.
    assert not any(t.startswith("project_") for t in sent.get("tags", []))


def test_remember_tags_the_project_the_caller_names(
    server: TestClient, cloud: FakeCloud, tmp_path: Path
) -> None:
    project = tmp_path / "acme-web"
    (project / ".git").mkdir(parents=True)
    headers = _activate(server)
    server.post(
        f"/api/v2/agents/{AGENT}/remember",
        json={"content": "Use pnpm", "type": "instruction"},
        headers={**headers, "X-Memanto-Project": str(project)},
    )
    sent = cloud.sent("POST", f"/agents/{AGENT}/remember")[-1]
    assert "project_acme_web" in sent["tags"]


def test_recall_returns_plain_content(server: TestClient, cloud: FakeCloud) -> None:
    headers = _activate(server)
    response = server.post(
        f"/api/v2/agents/{AGENT}/recall",
        json={"query": "theme", "limit": 5},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    memory = body["memories"][0]
    assert memory["content"] == "The user prefers dark mode"
    assert memory["title"] == "Dark mode"
    assert memory["score"] == 0.42
    assert cloud.sent("POST", f"/agents/{AGENT}/recall")[-1]["limit"] == 5


def test_recall_recent_and_changed_since(server: TestClient) -> None:
    headers = _activate(server)
    recent = server.post(
        f"/api/v2/agents/{AGENT}/recall/recent", json={"limit": 3}, headers=headers
    ).json()
    assert recent["temporal_mode"] == "recent"
    assert recent["memories"][0]["content"] == "The user prefers dark mode"

    changed = server.post(
        f"/api/v2/agents/{AGENT}/recall/changed-since",
        json={"since": "2026-11-01T00:00:00Z"},
        headers=headers,
    ).json()
    assert changed["temporal_mode"] == "changed_since"
    assert changed["memories"][0]["change_type"] == "created"


def test_answer_asks_cloud_without_streaming(
    server: TestClient, cloud: FakeCloud
) -> None:
    headers = _activate(server)
    body = server.post(
        f"/api/v2/agents/{AGENT}/answer",
        json={"question": "Theme?"},
        headers=headers,
    ).json()
    assert body["answer"] == "Dark mode."
    assert body["sources"][0]["id"] == "m1"
    assert cloud.sent("POST", f"/agents/{AGENT}/answer")[-1]["stream"] is False


def test_memory_calls_need_a_session_for_that_agent(server: TestClient) -> None:
    response = server.post(f"/api/v2/agents/{AGENT}/recall", json={"query": "theme"})
    assert response.status_code == 401


def test_cloud_key_rejection_is_not_a_session_401(
    server: TestClient, cloud: FakeCloud
) -> None:
    """A 401 from Memanto Cloud must not look like a bad session token.

    The extensions drop their token and activate again on a 401, which would
    loop forever when the problem is the server's ``mk_`` key.
    """
    headers = _activate(server)
    cloud.routes[("POST", f"/agents/{AGENT}/recall")] = httpx.Response(
        401, json={"detail": "Unauthorized"}
    )
    response = server.post(
        f"/api/v2/agents/{AGENT}/recall", json={"query": "theme"}, headers=headers
    )
    assert response.status_code == 502
    assert "memanto login" in response.text


def test_cloud_404_passes_through(server: TestClient) -> None:
    headers = _activate(server)
    response = server.post(
        f"/api/v2/agents/{AGENT}/memories/missing/expire", json={}, headers=headers
    )
    assert response.status_code == 404


def test_delete_agent_requires_confirming_memories_go_too(
    server: TestClient, cloud: FakeCloud
) -> None:
    assert server.delete(f"/api/v2/agents/{AGENT}").status_code == 400
    assert not cloud.sent("DELETE", f"/agents/{AGENT}")

    response = server.delete(f"/api/v2/agents/{AGENT}?delete-backup-too=true")
    assert response.status_code == 200
    assert len(cloud.sent("DELETE", f"/agents/{AGENT}")) == 1


def test_recall_all_is_not_available(server: TestClient) -> None:
    headers = _activate(server)
    response = server.post(
        f"/api/v2/agents/{AGENT}/recall/all", json={}, headers=headers
    )
    assert response.status_code == 501


def test_ui_points_to_the_console(server: TestClient) -> None:
    response = server.get("/ui", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/memory")


def test_without_the_flag_the_local_routes_are_mounted() -> None:
    import memanto.app.main as main_module

    paths = {getattr(r, "path", "") for r in main_module.app.routes}
    assert "/api/v2/agents/{agent_id}/recall/all" in paths
    # The local UI is mounted only in local mode.
    assert any(p.startswith("/ui") for p in paths)
    assert cloud_module.cloud_serve_enabled() is False


def test_remote_callers_need_the_memanto_cloud_key(server: TestClient) -> None:
    """Off loopback, management calls need the server's ``mk_`` key."""
    app = cast(_Loopback, server.app).app
    remote = TestClient(app, base_url="http://memanto.example:8000")
    assert remote.get("/api/v2/agents").status_code == 401
    assert (
        remote.get("/api/v2/agents", headers={"X-Api-Key": "mk_wrong"}).status_code
        == 401
    )
    assert (
        remote.get("/api/v2/agents", headers={"X-Api-Key": "mk_test"}).status_code
        == 200
    )


def test_serve_refuses_to_start_on_cloud_without_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from memanto.app.clients.backend import Backend
    from memanto.cli.commands import core as core_module
    from memanto.cli.config.manager import ConfigManager
    from memanto.cli.main import app as cli_app

    for var in ("MEMANTO_API_KEY", "MOORCHEH_API_KEY", cloud_module.CLOUD_SERVE_ENV):
        monkeypatch.delenv(var, raising=False)
    cm = ConfigManager(config_dir=tmp_path / ".memanto")
    cm.set_backend(Backend.MEMANTO_CLOUD)
    monkeypatch.setattr(core_module, "config_manager", cm)

    result = CliRunner().invoke(cli_app, ["serve", "--port", "8799"])
    assert result.exit_code != 0
    assert "memanto login" in result.output
    assert cloud_module.cloud_serve_enabled() is False

"""HostedClient: SdkClient interface over the Memanto Cloud public API (mocked HTTP)."""

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AuthenticationError,
    MemoryOperationError,
    SessionError,
)
from memanto.cli.client import hosted_client as hosted_module
from memanto.cli.client.hosted_client import HostedClient

BASE = "https://api.test"
AGENT = "hosted-agent"


class FakeApi:
    """Routes ``(method, path)`` to canned responses and records every request."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Any] = {
            ("GET", f"/agents/{AGENT}"): {"agent_id": AGENT, "pattern": "tool"},
        }
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(
                404, json={"message": "The current request is not defined by this API."}
            )
        if callable(route):
            return cast(httpx.Response, route(request))
        if isinstance(route, httpx.Response):
            return route
        return httpx.Response(200, json=route)

    def last_json(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.requests[-1].content))


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def client(api: FakeApi, tmp_path: Path, monkeypatch) -> HostedClient:
    monkeypatch.setattr(hosted_module.time, "sleep", lambda _s: None)
    c = HostedClient("mk_test", base_url=BASE, transport=httpx.MockTransport(api))
    c._session_service = SessionService(  # type: ignore[assignment]
        secret_key="test-secret-key-for-hosted-client-tests",
        sessions_dir=tmp_path / "sessions",
    )
    return c


@pytest.fixture
def active(client: HostedClient) -> HostedClient:
    client.activate_agent(AGENT)
    return client


# Sessions (local record only)


def test_activate_checks_agent_and_records_local_session(client, api):
    result = client.activate_agent(AGENT)

    assert [r.url.path for r in api.requests] == [f"/agents/{AGENT}"]
    assert result["agent_id"] == AGENT
    assert client.get_session_info()["agent_id"] == AGENT


def test_activate_missing_agent_raises_agent_not_found(client, api):
    with pytest.raises(AgentNotFoundError):
        client.activate_agent("missing")


def test_memory_ops_require_activation(client):
    with pytest.raises(SessionError):
        client.remember(AGENT, "fact", "t", "content")


# Requests and response shapes


def test_remember_sends_api_key_and_maps_response(active, api):
    api.routes[("POST", f"/agents/{AGENT}/remember")] = {
        "memory_id": "m1",
        "agent_id": AGENT,
        "status": "queued",
        "confidence": 0.9,
        "type": "fact",
    }

    result = active.remember(AGENT, "fact", "Title", "Body", confidence=0.9, tags=["a"])

    request = api.requests[-1]
    assert request.headers["x-api-key"] == "mk_test"
    assert request.headers["User-Agent"].startswith("memanto-cli/")
    assert api.last_json() == {
        "type": "fact",
        "title": "Title",
        "content": "Body",
        "confidence": 0.9,
        "tags": ["a"],
        "source": "user",
    }
    assert result == {
        "memory_id": "m1",
        "agent_id": AGENT,
        "namespace": AGENT,
        "status": "queued",
        "confidence": 0.9,
        "type": "fact",
    }


def test_remember_validates_input_locally(active, api):
    with pytest.raises(ValueError):
        active.remember(AGENT, "not-a-type", "t", "content")
    assert len(api.requests) == 1  # only the activation lookup


def test_batch_remember_returns_server_result(active, api):
    body = {
        "total_submitted": 1,
        "successful": 1,
        "failed": 0,
        "results": [{"id": "x"}],
    }
    api.routes[("POST", f"/agents/{AGENT}/batch-remember")] = body

    result = active.batch_remember(AGENT, [{"content": "c"}], source="claude-code")

    assert result == body
    assert api.last_json() == {"memories": [{"content": "c"}], "source": "claude-code"}


def test_recall_drops_unset_filters_and_maps_response(active, api):
    api.routes[("POST", f"/agents/{AGENT}/recall")] = {
        "agent_id": AGENT,
        "count": 1,
        "memories": [{"id": "m1"}],
        "query": "q",
    }

    result = active.recall(AGENT, "q", limit=5, type=["fact"], status="active")

    sent = api.last_json()
    assert sent["query"] == "q"
    assert sent["limit"] == 5
    assert sent["type"] == ["fact"]
    assert sent["status"] == "active"
    assert "tags" not in sent and "created_after" not in sent
    assert result == {
        "agent_id": AGENT,
        "query": "q",
        "memories": [{"id": "m1"}],
        "count": 1,
    }


@pytest.mark.parametrize(
    ("method", "kwargs", "route", "expected_body"),
    [
        ("recall_recent", {}, "recent", {"status": "all"}),
        ("recall_as_of", {"as_of": "2026-01-01"}, "as-of", {"as_of": "2026-01-01"}),
        (
            "recall_changed_since",
            {"since": "2026-01-01"},
            "changed-since",
            {"since": "2026-01-01", "status": "all"},
        ),
    ],
)
def test_temporal_recall_routes(active, api, method, kwargs, route, expected_body):
    api.routes[("POST", f"/agents/{AGENT}/recall/{route}")] = {
        "count": 0,
        "memories": [],
    }

    result = getattr(active, method)(AGENT, limit=3, **kwargs)

    assert api.last_json() == {"limit": 3, **expected_body}
    assert result["memories"] == [] and result["count"] == 0


def test_answer_lets_server_choose_model(active, api):
    api.routes[("POST", f"/agents/{AGENT}/answer")] = {
        "answer": "42",
        "sources": [{"id": "m1"}],
    }

    result = active.answer(AGENT, "why?")

    sent = api.last_json()
    assert sent["question"] == "why?"
    assert sent["stream"] is False
    assert "ai_model" not in sent
    assert result["answer"] == "42" and result["sources"] == [{"id": "m1"}]


def test_list_and_resolve_conflicts(active, api):
    api.routes[("GET", f"/agents/{AGENT}/conflicts")] = {
        "conflicts": [{"index": 2}],
        "count": 1,
    }
    api.routes[("POST", f"/agents/{AGENT}/conflicts/resolve")] = {"status": "resolved"}

    assert active.list_conflicts(AGENT, "2026-11-02") == [{"index": 2}]
    assert api.requests[-1].url.params["date"] == "2026-11-02"

    active.resolve_conflict(AGENT, "2026-11-02", 2, "keep_new")
    assert api.last_json() == {
        "date": "2026-11-02",
        "conflict_index": 2,
        "action": "keep_new",
    }


def test_sync_memory_to_project_renders_hosted_recall(
    active, api, tmp_path, monkeypatch
):
    """The SessionStart hook path (`memanto memory sync`) works on Memanto Cloud."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    def recall(request):
        body = json.loads(request.content)
        if body["type"] == ["fact"]:
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "memories": [
                        {
                            "id": "m1",
                            "type": "fact",
                            "title": "Sky",
                            "content": "Sky is blue",
                            "confidence": 0.9,
                            "created_at": "2026-11-02T00:00:00+00:00",
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"count": 0, "memories": []})

    api.routes[("POST", f"/agents/{AGENT}/recall")] = recall
    project = tmp_path / "project"

    result = active.sync_memory_to_project(AGENT, str(project))

    assert result["source"] == "fresh" and result["total_memories"] == 1
    assert "Sky is blue" in (project / "MEMORY.md").read_text(encoding="utf-8")


def test_upload_file_puts_bytes_to_signed_url_without_api_key(
    active, api, tmp_path, monkeypatch
):
    api.routes[("POST", f"/agents/{AGENT}/files")] = {
        "file_id": "f1",
        "job_id": "j1",
        "file_name": "notes.md",
        "content_type": "text/markdown",
        "upload_url": "https://storage.test/signed",
    }
    puts: list[dict[str, Any]] = []

    def fake_put(url, content, headers, timeout):
        puts.append({"url": url, "content": content, "headers": headers})
        return httpx.Response(200)

    monkeypatch.setattr(hosted_module.httpx, "put", fake_put)
    path = tmp_path / "notes.md"
    path.write_text("hello", encoding="utf-8")

    result = active.upload_file(AGENT, str(path))

    assert api.last_json() == {"file_name": "notes.md", "size_bytes": 5}
    assert puts == [
        {
            "url": "https://storage.test/signed",
            "content": b"hello",
            "headers": {"Content-Type": "text/markdown"},
        }
    ]
    assert result["success"] is True and result["job_id"] == "j1"


# Errors


def test_401_tells_user_to_log_in(client, api):
    api.routes[("GET", "/agents")] = httpx.Response(
        401, json={"error": "Missing x-api-key header"}
    )

    with pytest.raises(AuthenticationError, match="memanto login"):
        client.list_agents()


def test_409_maps_to_agent_already_exists(client, api):
    api.routes[("POST", "/agents")] = httpx.Response(409, json={"message": "exists"})

    with pytest.raises(AgentAlreadyExistsError):
        client.create_agent("dup")


def test_gateway_errors_are_retried(client, api):
    responses = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"agents": []}),
    ]
    api.routes[("GET", "/agents")] = lambda _r: responses.pop(0)

    assert client.list_agents() == {"agents": []}
    assert len(api.requests) == 3


def test_500_is_not_retried(client, api):
    api.routes[("GET", "/agents")] = httpx.Response(500, json={"message": "boom"})

    with pytest.raises(ConnectionError, match="boom"):
        client.list_agents()
    assert len(api.requests) == 1


def test_plan_limit_message_points_to_billing(client, api):
    api.routes[("GET", "/agents")] = httpx.Response(
        402, json={"message": "api_calls limit reached"}
    )

    with pytest.raises(MemoryOperationError, match="/billing"):
        client.list_agents()


def test_get_account_returns_none_when_server_has_no_me(client):
    assert client.get_account() is None


def test_nested_detail_error_message_is_shown(client, api):
    api.routes[("GET", "/agents")] = httpx.Response(
        422,
        json={
            "detail": {"error": "ValidationError", "message": "agent_id is required"}
        },
    )

    with pytest.raises(ValueError, match="agent_id is required"):
        client.list_agents()


def test_sign_out_device_deletes_key(client, api):
    api.routes[("POST", "/cli/logout")] = {"message": "Signed out"}

    assert client.sign_out_device() is True
    assert api.requests[-1].headers["x-api-key"] == "mk_test"


def test_sign_out_device_leaves_console_key(client, api):
    api.routes[("POST", "/cli/logout")] = httpx.Response(
        400, json={"detail": {"error": "NotADeviceKey", "message": "console key"}}
    )

    assert client.sign_out_device() is False


def test_sign_out_device_on_server_without_route_raises(client):
    with pytest.raises(hosted_module.HostedRequestError) as info:
        client.sign_out_device()
    assert info.value.status_code == 404


def test_sign_out_device_with_dead_key_raises(client, api):
    api.routes[("POST", "/cli/logout")] = httpx.Response(401, json={"detail": "no"})

    with pytest.raises(AuthenticationError):
        client.sign_out_device()


def test_local_moorcheh_paths_are_blocked(client):
    with pytest.raises(
        MemoryOperationError, match="Not available on Memanto Cloud yet"
    ):
        client._get_moorcheh()


def test_delete_agent_requires_deleting_memories(client):
    with pytest.raises(ValueError, match="cannot be kept"):
        client.delete_agent(AGENT)


def test_delete_agent_deletes_and_clears_session(active, api):
    api.routes[("DELETE", f"/agents/{AGENT}")] = {"message": "deleted"}

    result = active.delete_agent(AGENT, delete_memories=True)

    assert result == {"status": "deleted", "agent_id": AGENT, "memories_deleted": True}
    assert active.agent_id is None

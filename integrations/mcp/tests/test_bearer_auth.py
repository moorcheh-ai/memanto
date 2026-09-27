"""Inbound Bearer auth for MCP HTTP/SSE when MEMANTO_MCP_AUTH_TOKEN is set."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from memanto_mcp.auth import apply_bearer_auth
from memanto_mcp.config import MCPServerSettings, TransportType
from memanto_mcp.server import build_http_app, build_server


def _plain_app():
    async def ok(_request):
        return PlainTextResponse("ok")

    return Starlette(routes=[Route("/", ok)])


def test_bearer_middleware_rejects_missing_token() -> None:
    app = apply_bearer_auth(_plain_app(), "secret-token")
    client = TestClient(app)
    assert client.get("/").status_code == 401


def test_bearer_middleware_accepts_authorization_header() -> None:
    app = apply_bearer_auth(_plain_app(), "secret-token")
    client = TestClient(app)
    resp = client.get("/", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_bearer_middleware_accepts_x_api_key() -> None:
    app = apply_bearer_auth(_plain_app(), "secret-token")
    client = TestClient(app)
    resp = client.get("/", headers={"X-Api-Key": "secret-token"})
    assert resp.status_code == 200


def test_bearer_middleware_rejects_wrong_token() -> None:
    app = apply_bearer_auth(_plain_app(), "secret-token")
    client = TestClient(app)
    resp = client.get("/", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_tokens_match_handles_non_ascii() -> None:
    from memanto_mcp.auth import _tokens_match

    token = "sécrèt-🔑-token"
    assert _tokens_match(token, token) is True
    assert _tokens_match(token, "other") is False
    assert _tokens_match("ascii-only", "ascii-only") is True


def test_build_http_app_enforces_token(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_AUTH_TOKEN", "shared-secret")
    settings = MCPServerSettings(
        transport=TransportType.STREAMABLE_HTTP,
        host="127.0.0.1",
    )
    mcp = build_server(settings)
    app = build_http_app(mcp, settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/mcp").status_code == 401
        # GET may be a 4xx for the MCP endpoint, but must not be a server error.
        authed = client.get(
            "/mcp", headers={"Authorization": "Bearer shared-secret"}
        )
        assert authed.status_code < 500
        assert authed.status_code != 401

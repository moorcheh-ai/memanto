"""Unit tests for the MCP server's inbound network-auth boundary."""

from __future__ import annotations

from typing import Any

import pytest

from memanto_mcp.auth import MCPInboundAuthMiddleware


async def _run_request(
    app: MCPInboundAuthMiddleware,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 43210),
    scope_type: str = "http",
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope: dict[str, Any] = {
        "type": scope_type,
        "headers": headers or [],
        "client": client,
    }
    await app(scope, receive, send)
    return messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"authorization", b"Basic secret")],
        [(b"authorization", b"Bearer wrong")],
        [(b"authorization", b"Bearer secret"), (b"authorization", b"Bearer secret")],
    ],
)
async def test_configured_token_rejects_missing_or_invalid_credentials(
    headers: list[tuple[bytes, bytes]],
) -> None:
    called = False

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    app = MCPInboundAuthMiddleware(downstream, "secret")
    messages = await _run_request(app, headers=headers, client=("203.0.113.10", 1))

    assert messages[0]["status"] == 401
    assert messages[0]["headers"][-1] == (b"www-authenticate", b"Bearer")
    assert b"secret" not in messages[1]["body"]
    assert not called


@pytest.mark.asyncio
async def test_configured_token_allows_valid_bearer_credentials() -> None:
    called = False

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    app = MCPInboundAuthMiddleware(downstream, "secret")
    messages = await _run_request(
        app,
        headers=[(b"Authorization", b"bearer secret")],
        client=("203.0.113.10", 1),
    )

    assert messages == []
    assert called


@pytest.mark.asyncio
async def test_unconfigured_token_only_allows_loopback_peers() -> None:
    called = False

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    app = MCPInboundAuthMiddleware(downstream, None)
    local_messages = await _run_request(app, client=("127.0.0.1", 1))
    assert local_messages == []
    assert called

    called = False
    remote_messages = await _run_request(app, client=("203.0.113.10", 1))
    assert remote_messages[0]["status"] == 403
    assert not called


@pytest.mark.asyncio
async def test_non_http_scopes_bypass_http_auth() -> None:
    called = False

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    app = MCPInboundAuthMiddleware(downstream, "secret")
    await _run_request(app, scope_type="lifespan", client=None)
    assert called

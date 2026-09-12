"""Inbound authentication for network MCP transports.

The Moorcheh API key authenticates Memanto *to* Moorcheh. It must not be
treated as authentication for clients connecting *to* this MCP server. The
network transports therefore use a separate bearer token, while the default
loopback-only mode remains convenient for local MCP clients.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest

from starlette.types import Receive, Scope, Send

from memanto_mcp.config import is_loopback_host

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_UNAUTHORIZED_BODY = b'{"detail":"Unauthorized"}'
_FORBIDDEN_BODY = b'{"detail":"Loopback access required"}'


def _bearer_token(scope: Scope) -> str | None:
    """Extract one well-formed bearer token from an ASGI HTTP scope."""
    authorization_headers = [
        value
        for name, value in scope.get("headers", [])
        if name.lower() == b"authorization"
    ]
    if len(authorization_headers) != 1:
        return None

    parts = authorization_headers[0].split(None, 1)
    if len(parts) != 2 or parts[0].lower() != b"bearer":
        return None
    token = parts[1].strip()
    return token.decode("latin-1") if token else None


def _peer_is_loopback(scope: Scope) -> bool:
    client = scope.get("client")
    return bool(client and is_loopback_host(str(client[0])))


async def _send_error(send: Send, status: int, body: bytes) -> None:
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class MCPInboundAuthMiddleware:
    """Protect every HTTP request before it reaches an MCP transport app.

    A configured token is required for every HTTP request. Without a token,
    only loopback peers are accepted; configuration validation prevents that
    mode from being used with a non-loopback bind address.
    """

    def __init__(self, app: ASGIApp, auth_token: str | None) -> None:
        self.app = app
        self.auth_token = auth_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.auth_token is None:
            if not _peer_is_loopback(scope):
                await _send_error(send, 403, _FORBIDDEN_BODY)
                return
        else:
            supplied_token = _bearer_token(scope)
            if supplied_token is None or not compare_digest(
                supplied_token, self.auth_token
            ):
                await _send_error(send, 401, _UNAUTHORIZED_BODY)
                return

        await self.app(scope, receive, send)

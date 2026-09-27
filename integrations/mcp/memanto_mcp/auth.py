"""Inbound Bearer auth for MCP HTTP / SSE transports."""

from __future__ import annotations

import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Reject HTTP requests that do not present the expected Bearer token.

    Used when ``MEMANTO_MCP_AUTH_TOKEN`` is configured so HTTP/SSE endpoints
    authenticate inbound clients (including traffic forwarded from a TLS
    reverse proxy to the loopback listener).
    """

    def __init__(self, app, expected_token: str):
        super().__init__(app)
        self._expected = expected_token

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        presented = _extract_bearer(request)
        if presented is None or not _tokens_match(presented, self._expected):
            return JSONResponse(
                {"error": "Unauthorized", "message": "Valid Bearer token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


def _tokens_match(presented: str, expected: str) -> bool:
    """Constant-time compare using UTF-8 bytes (safe for non-ASCII secrets)."""
    try:
        return secrets.compare_digest(
            presented.encode("utf-8"),
            expected.encode("utf-8"),
        )
    except (TypeError, UnicodeEncodeError):
        return False


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and isinstance(auth, str):
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    # Also accept X-Api-Key for clients that cannot set Authorization.
    api_key = request.headers.get("x-api-key")
    if api_key and isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def apply_bearer_auth(app, token: str | None):
    """Attach Bearer middleware when a token is configured; no-op otherwise."""
    if token:
        app.add_middleware(BearerTokenMiddleware, expected_token=token)
    return app

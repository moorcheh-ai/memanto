"""
Tests for trusted-proxy scheme restoration (MEMANTO_PROXY_ALLOWED_IPS).

When TLS terminates at a reverse proxy, X-Forwarded-Proto carries the
browser-facing scheme. The middleware may only honor that header from an
explicit allowlist of proxy peers; otherwise a random client could force the
session cookie's Secure flag on or off.
"""

import asyncio
import logging

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from memanto.app.config import settings
from memanto.app.middleware import TrustedProxySchemeMiddleware
from memanto.app.routes.auth_deps import set_session_cookie

TRUSTED_PEER = "10.0.0.5"
UNTRUSTED_PEER = "203.0.113.9"


def _run_middleware(scope: dict, allowed_ips: list[str]) -> str:
    """Drive the middleware against a stub ASGI child that reports the scheme."""
    seen: dict[str, str] = {}

    async def child(scope_: dict, receive, send) -> None:
        seen["scheme"] = scope_.get("scheme") or ""

    async def noop_receive():
        return {}

    middleware = TrustedProxySchemeMiddleware(child, allowed_ips)
    asyncio.run(middleware(scope, noop_receive, lambda m: None))
    return seen["scheme"]


def _http_scope(peer: str, proto: str | None) -> dict:
    headers = []
    if proto is not None:
        headers.append((b"x-forwarded-proto", proto.encode("latin-1")))
    return {
        "type": "http",
        "scheme": "http",
        "client": (peer, 50000),
        "headers": headers,
    }


class TestTrustedProxySchemeMiddleware:
    def test_trusted_peer_forwarded_https(self):
        scope = _http_scope(TRUSTED_PEER, "https")
        assert _run_middleware(scope, [TRUSTED_PEER]) == "https"

    def test_trusted_peer_forwarded_http(self):
        scope = _http_scope(TRUSTED_PEER, "http")
        assert _run_middleware(scope, [TRUSTED_PEER]) == "http"

    def test_trusted_peer_no_header_unchanged(self):
        scope = _http_scope(TRUSTED_PEER, None)
        assert _run_middleware(scope, [TRUSTED_PEER]) == "http"

    def test_untrusted_peer_header_ignored(self):
        scope = _http_scope(UNTRUSTED_PEER, "https")
        assert _run_middleware(scope, [TRUSTED_PEER]) == "http"

    def test_bogus_proto_ignored(self):
        scope = _http_scope(TRUSTED_PEER, "ftp")
        assert _run_middleware(scope, [TRUSTED_PEER]) == "http"

    def test_uppercase_proto_normalized(self):
        scope = _http_scope(TRUSTED_PEER, "HTTPS")
        assert _run_middleware(scope, [TRUSTED_PEER]) == "https"

    def test_empty_allowlist_never_trusts(self):
        scope = _http_scope(UNTRUSTED_PEER, "https")
        assert _run_middleware(scope, []) == "http"

    def test_non_http_scope_unaffected(self):
        scope = {"type": "websocket", "scheme": "ws", "client": (TRUSTED_PEER, 1)}
        assert _run_middleware(scope, [TRUSTED_PEER]) == "ws"


class TestProxySettingsDefault:
    def test_proxy_allowed_ips_defaults_empty(self):
        assert settings.MEMANTO_PROXY_ALLOWED_IPS == ""
        assert settings.proxy_allowed_ips == []

    def test_proxy_allowed_ips_parses_comma_list(self, monkeypatch):
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "10.0.0.5,10.0.0.6")
        assert settings.proxy_allowed_ips == ["10.0.0.5", "10.0.0.6"]

    def test_proxy_allowed_ips_parses_json(self, monkeypatch):
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", '["10.0.0.5"]')
        assert settings.proxy_allowed_ips == ["10.0.0.5"]

    def test_proxy_allowed_ips_ignores_empty_string(self, monkeypatch):
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "")
        assert settings.proxy_allowed_ips == []


def _proxy_client(allowed_ips: list[str], peer: str) -> TestClient:
    """TestClient whose peer address is forced to ``peer`` before routing.

    TestClient cannot change its own scope client, so wrap the middleware in an
    outer ASGI callable that sets the client before delegating.
    """

    async def login(request) -> JSONResponse:
        response = JSONResponse({"ok": True})
        set_session_cookie(response, "token123", request)
        return response

    app = Starlette(routes=[Route("/login", login)])
    middleware = TrustedProxySchemeMiddleware(app, allowed_ips)

    async def outer(scope: dict, receive, send) -> None:
        scope["client"] = (peer, 50001)
        await middleware(scope, receive, send)

    return TestClient(outer)


class TestCookieBehindProxy:
    def test_forwarded_https_sets_secure(self):
        client = _proxy_client([TRUSTED_PEER], TRUSTED_PEER)
        response = client.get("/login", headers={"X-Forwarded-Proto": "https"})
        assert "Secure" in response.headers["set-cookie"]

    def test_untrusted_proxy_keeps_cookie_plain(self, caplog):
        client = _proxy_client([TRUSTED_PEER], UNTRUSTED_PEER)
        with caplog.at_level(logging.WARNING, logger="memanto.app.routes.auth_deps"):
            response = client.get("/login", headers={"X-Forwarded-Proto": "https"})
        assert "Secure" not in response.headers["set-cookie"]
        assert "plain HTTP" in caplog.text

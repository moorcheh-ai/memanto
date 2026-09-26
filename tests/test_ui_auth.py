"""Tests for unauthenticated UI endpoint vulnerability fix."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _make_app():
    """Create a minimal FastAPI app with just the UI router, bypassing startup deps."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from memanto.app.ui.routes.ui_router import router as ui_router

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ui_router)
    return app


class _LoopbackClient:
    """ASGI wrapper that makes TestClient requests look like loopback traffic."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = ("127.0.0.1", 50000)
        await self.app(scope, receive, send)


def _make_loopback_client(app):
    return TestClient(_LoopbackClient(app), raise_server_exceptions=False)


class TestUnauthenticatedUIEndpoints:
    """Unauthenticated requests from non-localhost must be refused with HTTP 403.

    The UI router exposes management endpoints (shutdown, filesystem browse,
    config update, API-key replacement, on-prem restart) with no token-based
    authentication.  Without a localhost-origin guard any host that can reach
    the server process can kill it, read directory listings, or replace the
    stored API key.
    """

    def test_shutdown_rejected_from_remote(self):
        """POST /api/ui/shutdown must return 403 for a non-local request."""
        app = _make_app()
        # Starlette TestClient uses "testclient" as the host — not 127.0.0.1
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/ui/shutdown")
        # "testclient" is not a loopback address → must be 403
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

    def test_browse_rejected_from_remote(self):
        """GET /api/ui/browse?path=/etc must return 403 for a non-local request."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/ui/browse?path=/etc")
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

    def test_update_config_rejected_from_remote(self):
        """PATCH /api/ui/config must return 403 for a non-local request."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch("/api/ui/config", json={})
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

    def test_update_api_key_rejected_from_remote(self):
        """PUT /api/ui/api-key must return 403 for a non-local request."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put("/api/ui/api-key", json={"api_key": "stolen"})
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

    def test_loopback_cross_site_origin_rejected(self):
        """Local browser requests from another website must not reach UI endpoints."""
        app = _make_app()
        client = _make_loopback_client(app)
        resp = client.post(
            "/api/ui/shutdown",
            headers={"Origin": "https://evil.example"},
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"
        assert resp.json()["detail"] == (
            "UI management endpoints reject cross-site browser requests."
        )

    def test_loopback_cross_site_fetch_metadata_rejected(self):
        """Fetch Metadata blocks no-cors style cross-site POSTs without Origin."""
        app = _make_app()
        client = _make_loopback_client(app)
        resp = client.post(
            "/api/ui/shutdown",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"
        assert resp.json()["detail"] == (
            "UI management endpoints reject cross-site browser requests."
        )


class TestLoopbackDetection:
    """Unit tests for the _is_loopback helper used by _require_local.

    Covers all loopback address forms so the guard is not bypassable via
    address variants not included in the original string-literal check.
    """

    def test_ipv4_loopback_accepted(self):
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback("127.0.0.1") is True

    def test_ipv6_loopback_accepted(self):
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback("::1") is True

    def test_ipv4_mapped_ipv6_loopback_accepted(self):
        """::ffff:127.0.0.1 is the IPv4-mapped form of 127.0.0.1 — must pass."""
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback("::ffff:127.0.0.1") is True

    def test_remote_ipv4_rejected(self):
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback("192.168.1.100") is False

    def test_none_rejected(self):
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback(None) is False

    def test_testclient_host_rejected(self):
        """Starlette TestClient sends host="testclient" — must be treated as remote."""
        from memanto.app.ui.routes.ui_router import _is_loopback

        assert _is_loopback("testclient") is False

    def test_loopback_origin_accepted(self):
        """Same-origin UI requests from localhost must be allowed."""
        from memanto.app.routes.auth_deps import _is_loopback_origin

        assert _is_loopback_origin("http://localhost:8000") is True
        assert _is_loopback_origin("http://127.0.0.1:8000") is True
        assert _is_loopback_origin("http://[::1]:8000") is True

    def test_remote_origin_rejected(self):
        from memanto.app.routes.auth_deps import _is_loopback_origin

        assert _is_loopback_origin("https://evil.example") is False

    def test_require_local_allows_loopback(self):
        """_require_local must not raise for a 127.0.0.1 caller."""
        from memanto.app.ui.routes.ui_router import _require_local

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"host": "127.0.0.1:8000"}
        asyncio.run(_require_local(mock_request))  # must not raise

    def test_require_local_allows_ipv4_mapped_loopback(self):
        """_require_local must not raise for a ::ffff:127.0.0.1 caller."""
        from memanto.app.ui.routes.ui_router import _require_local

        mock_request = MagicMock()
        mock_request.client.host = "::ffff:127.0.0.1"
        mock_request.headers = {"host": "127.0.0.1:8000"}
        asyncio.run(_require_local(mock_request))  # must not raise


class TestDNSRebindingGuard:
    """DNS-rebinding regression tests for _require_local.

    A rebound domain keeps the TCP peer at 127.0.0.1 while the browser sends
    ``Host: <attacker-domain>``. Same-origin after rebind means requests carry
    ``Sec-Fetch-Site: same-origin`` and no Origin header on GETs, so neither
    the client-IP check nor the cross-site check can see the attack — only a
    Host-header allowlist can. Without it, a malicious page could drive the
    whole ``/api/ui/*`` surface (config leak + session-cookie issuance,
    filesystem browse, migrate file reads, api-key overwrite, connections
    install file writes) and then ride the planted session cookie into the
    session-authenticated ``/api/v2`` memory endpoints.
    """

    def test_ui_config_rejects_non_loopback_host(self):
        """GET /api/ui/config with Host: attacker.com must return 403."""
        app = _make_app()
        client = _make_loopback_client(app)
        resp = client.get(
            "/api/ui/config",
            headers={
                "Host": "attacker.com:8000",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"
        assert "memanto_session_token" not in resp.headers.get(
            "set-cookie", ""
        ), "rebound request must not receive the session cookie"

    def test_browse_rejects_non_loopback_host(self):
        """GET /api/ui/browse with Host: attacker.com must return 403."""
        app = _make_app()
        client = _make_loopback_client(app)
        resp = client.get(
            "/api/ui/browse?path=/",
            headers={
                "Host": "attacker.com:8000",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

    def test_missing_host_rejected(self):
        """Requests without a Host header must not inherit loopback trust."""
        from memanto.app.ui.routes.ui_router import _require_local

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}
        with pytest.raises(HTTPException) as exc:
            asyncio.run(_require_local(mock_request))
        assert exc.value.status_code == 403

    def test_loopback_host_accepted(self):
        """Loopback peer + loopback Host header must still pass."""
        app = _make_app()
        client = _make_loopback_client(app)
        # Endpoint needs no configured backend for the auth decision itself;
        # any non-403 means the guard let the request through.
        resp = client.get(
            "/api/ui/config",
            headers={
                "Host": "127.0.0.1:8000",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert resp.status_code != 403, f"expected pass, got {resp.status_code}"


class TestCookieAuthHostBinding:
    """get_current_session must reject cookie auth from non-loopback Hosts.

    The session cookie (SameSite=strict, HttpOnly) is only issued to the
    local UI. A rebound origin is same-site with itself, so the browser sends
    the cookie — the Host header is the only signal that the request did not
    come from the real local UI. Header auth (X-Session-Token) stays open for
    remote API clients and is not covered by this check.
    """

    def _call(self, host):
        from memanto.app.routes.auth_deps import get_current_session

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"host": host} if host else {}
        return get_current_session(
            request=mock_request,
            response=MagicMock(),
            x_session_token=None,
            session_cookie="some.jwt.token",
            authorization=None,
            x_api_key=None,
        )

    def test_cookie_auth_rejects_non_loopback_host(self):
        with pytest.raises(HTTPException) as exc:
            self._call("attacker.com:8000")
        assert exc.value.status_code == 403

    def test_cookie_auth_rejects_missing_host(self):
        with pytest.raises(HTTPException) as exc:
            self._call(None)
        assert exc.value.status_code == 403

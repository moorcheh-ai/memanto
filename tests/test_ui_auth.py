"""Tests for unauthenticated UI endpoint vulnerability fix."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


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

    def test_require_local_allows_loopback(self):
        """_require_local must not raise for a 127.0.0.1 caller."""
        from memanto.app.ui.routes.ui_router import _require_local
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        asyncio.run(_require_local(mock_request))  # must not raise

    def test_require_local_allows_ipv4_mapped_loopback(self):
        """_require_local must not raise for a ::ffff:127.0.0.1 caller."""
        from memanto.app.ui.routes.ui_router import _require_local
        mock_request = MagicMock()
        mock_request.client.host = "::ffff:127.0.0.1"
        asyncio.run(_require_local(mock_request))  # must not raise

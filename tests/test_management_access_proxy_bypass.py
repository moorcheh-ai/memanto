"""
Regression tests for CWE-290 loopback-trust bypass on the API v2 management
endpoints (``require_management_access``).

The management endpoints grant full agent-lifecycle + memory read/write access.
They trusted any request whose ``request.client.host`` was loopback, but a
reverse proxy on localhost (the standard way to add TLS to the shipped
``HOST=0.0.0.0`` / no-TLS deployment) makes ``request.client.host`` the proxy's
loopback address for *every* external request.

These tests verify:
1. A direct loopback client with no forwarding headers is still trusted.
2. A loopback client presenting ``X-Forwarded-For`` is NOT trusted when no
   trusted proxy is configured (the safe default) -> 401.
3. A loopback client presenting ``X-Forwarded-For`` IS trusted when its address
   is listed in ``TRUSTED_PROXIES``.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    from memanto.app.config import settings

    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "test-server-key")
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])
    yield settings


def _mock_request(client_host: str, headers: dict) -> MagicMock:
    req = MagicMock()
    req.client.host = client_host
    req.headers = headers
    return req


def _call(client_host: str, headers: dict):
    from memanto.app.routes.auth_deps import require_management_access

    # Pass the credential args explicitly: as a FastAPI dependency their defaults
    # are ``Header`` sentinels, not None.
    return require_management_access(
        _mock_request(client_host, headers), authorization=None, x_api_key=None
    )


class TestManagementAccessLoopbackTrust:
    def test_direct_loopback_still_trusted(self):
        """Direct 127.0.0.1 client with no forwarding headers is trusted."""
        result = _call("127.0.0.1", {"host": "localhost"})
        assert result == "test-server-key"

    def test_loopback_with_forwarded_for_rejected_when_no_trusted_proxy(self):
        """Loopback client behind an untrusted proxy must NOT be trusted."""
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "x-forwarded-for": "203.0.113.9"})
        assert exc.value.status_code == 401

    def test_loopback_with_x_real_ip_rejected_when_no_trusted_proxy(self):
        """X-Real-IP is likewise treated as proxied and untrusted by default."""
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "x-real-ip": "203.0.113.9"})
        assert exc.value.status_code == 401

    def test_loopback_with_forwarded_for_trusted_when_proxy_configured(self, _configure):
        """A configured trusted proxy may still be loopback-trusted."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        result = _call("127.0.0.1", {"host": "localhost", "x-forwarded-for": "203.0.113.9"})
        assert result == "test-server-key"

    def test_remote_client_rejected_even_without_forwarded_headers(self):
        """A non-loopback direct client is never trusted."""
        with pytest.raises(HTTPException) as exc:
            _call("203.0.113.9", {"host": "example.com"})
        assert exc.value.status_code == 401

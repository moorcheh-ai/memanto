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
2. A loopback peer presenting forwarding headers is NOT trusted when no trusted
   proxy is configured (the safe default) -> 401.
3. A *trusted* proxy does NOT automatically mean a *trusted* client: the
   effective forwarded client IP must itself be loopback, with every forwarding
   header agreeing, or the request is rejected (401). A public-IP client behind
   a trusted proxy is rejected.
4. Malformed / conflicting forwarding headers are rejected (401).
5. ``X-Forwarded-For`` / ``X-Real-IP`` / ``Forwarded`` are all covered, and
   multi-level ``X-Forwarded-For`` cannot be tricked by prepending a spoofed
   loopback address.
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
    # --- 1. direct loopback, no proxy -------------------------------------
    def test_direct_loopback_still_trusted(self):
        """Direct 127.0.0.1 client with no forwarding headers is trusted."""
        result = _call("127.0.0.1", {"host": "localhost"})
        assert result == "test-server-key"

    def test_direct_ipv6_loopback_still_trusted(self):
        """Direct ::1 client with no forwarding headers is trusted."""
        result = _call("::1", {"host": "localhost"})
        assert result == "test-server-key"

    def test_remote_client_rejected_even_without_forwarded_headers(self):
        """A non-loopback direct client is never trusted."""
        with pytest.raises(HTTPException) as exc:
            _call("203.0.113.9", {"host": "example.com"})
        assert exc.value.status_code == 401

    # --- 2. untrusted proxy presenting forwarding headers -----------------
    def test_loopback_with_forwarded_for_rejected_when_no_trusted_proxy(self):
        """Loopback peer behind an untrusted proxy must NOT be trusted."""
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "x-forwarded-for": "203.0.113.9"})
        assert exc.value.status_code == 401

    def test_loopback_with_x_real_ip_rejected_when_no_trusted_proxy(self):
        """X-Real-IP is likewise treated as proxied and untrusted by default."""
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "x-real-ip": "203.0.113.9"})
        assert exc.value.status_code == 401

    def test_loopback_with_forwarded_rejected_when_no_trusted_proxy(self):
        """Standard Forwarded header is likewise treated as proxied/untrusted."""
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {"host": "localhost", "forwarded": "for=203.0.113.9"},
            )
        assert exc.value.status_code == 401

    # --- 3. trusted proxy, EFFECTIVE client must be loopback --------------
    def test_trusted_proxy_with_loopback_xff_allowed(self, _configure):
        """Trusted proxy forwarding a loopback client (127.0.0.1) is trusted."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        result = _call("127.0.0.1", {"host": "localhost", "x-forwarded-for": "127.0.0.1"})
        assert result == "test-server-key"

    def test_trusted_proxy_with_public_xff_rejected(self, _configure):
        """Trusted proxy is NOT a trusted client: public XFF -> 401."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {"host": "localhost", "x-forwarded-for": "203.0.113.9"},
            )
        assert exc.value.status_code == 401

    def test_trusted_proxy_with_no_forwarded_headers_rejected(self, _configure):
        """Trusted proxy but no forwarding headers -> client undeterminable -> 401."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost"})
        assert exc.value.status_code == 401

    # --- 5. malformed / conflicting headers -------------------------------
    def test_trusted_proxy_with_malformed_xff_rejected(self, _configure):
        """Malformed X-Forwarded-For is rejected."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {"host": "localhost", "x-forwarded-for": "not-an-ip"},
            )
        assert exc.value.status_code == 401

    def test_trusted_proxy_with_malformed_ip_xff_rejected(self, _configure):
        """An unparsable numeric/bracket token in XFF is rejected."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {"host": "localhost", "x-forwarded-for": "999.999.999.999"},
            )
        assert exc.value.status_code == 401

    def test_trusted_proxy_with_conflicting_headers_rejected(self, _configure):
        """X-Forwarded-For and X-Real-IP that disagree -> 401."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {
                    "host": "localhost",
                    "x-forwarded-for": "127.0.0.1",
                    "x-real-ip": "203.0.113.9",
                },
            )
        assert exc.value.status_code == 401

    # --- 8. X-Real-IP / Forwarded coverage --------------------------------
    def test_trusted_proxy_x_real_ip_loopback_allowed(self, _configure):
        """Trusted proxy forwarding a loopback client via X-Real-IP -> allowed."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        result = _call("127.0.0.1", {"host": "localhost", "x-real-ip": "127.0.0.1"})
        assert result == "test-server-key"

    def test_trusted_proxy_x_real_ip_public_rejected(self, _configure):
        """Trusted proxy forwarding a public client via X-Real-IP -> 401."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "x-real-ip": "203.0.113.9"})
        assert exc.value.status_code == 401

    def test_trusted_proxy_forwarded_header_loopback_allowed(self, _configure):
        """Trusted proxy forwarding a loopback client via Forwarded -> allowed."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        result = _call(
            "127.0.0.1",
            {"host": "localhost", "forwarded": "for=127.0.0.1"},
        )
        assert result == "test-server-key"

    def test_trusted_proxy_forwarded_header_public_rejected(self, _configure):
        """Trusted proxy forwarding a public client via Forwarded -> 401."""
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call("127.0.0.1", {"host": "localhost", "forwarded": "for=203.0.113.9"})
        assert exc.value.status_code == 401

    def test_trusted_proxy_forwarded_ipv6_loopback_allowed(self, _configure):
        """IPv6 loopback client via Forwarded for=\"[::1]\" -> allowed."""
        _configure.TRUSTED_PROXIES = ["::1"]
        result = _call(
            "::1",
            {"host": "localhost", "forwarded": 'for="[::1]:8080"'},
        )
        assert result == "test-server-key"

    # --- 7/9. multi-level X-Forwarded-For, no "wrong address" trust -------
    def test_multilevel_xff_attacker_spoof_rejected(self, _configure):
        """Attacker prepends a spoofed loopback address: rightmost (real) wins.

        ``127.0.0.1, 203.0.113.9`` -> proxy appended the real client
        (203.0.113.9). Taking the rightmost entry (not the spoofed leftmost)
        rejects it. Proves "trusted proxy != trusted client".
        """
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {
                    "host": "localhost",
                    "x-forwarded-for": "127.0.0.1, 203.0.113.9",
                },
            )
        assert exc.value.status_code == 401

    def test_multilevel_xff_proxy_appended_peer_rejected(self, _configure):
        """Proxy appends its own loopback peer: effective client is public -> 401.

        ``203.0.113.9, 127.0.0.1`` -> trailing 127.0.0.1 is stripped as the
        proxy's own peer, leaving 203.0.113.9 as the effective client.
        """
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        with pytest.raises(HTTPException) as exc:
            _call(
                "127.0.0.1",
                {
                    "host": "localhost",
                    "x-forwarded-for": "203.0.113.9, 127.0.0.1",
                },
            )
        assert exc.value.status_code == 401

    def test_multilevel_xff_proxy_appended_own_peer_loopback_allowed(self, _configure):
        """Proxy appended its own loopback peer; real client is loopback -> allowed.

        ``127.0.0.2, 127.0.0.1`` -> rightmost (127.0.0.1) is the proxy's own
        peer, so the effective client steps left to 127.0.0.2 (loopback).
        """
        _configure.TRUSTED_PROXIES = ["127.0.0.1"]
        result = _call(
            "127.0.0.1",
            {"host": "localhost", "x-forwarded-for": "127.0.0.2, 127.0.0.1"},
        )
        assert result == "test-server-key"

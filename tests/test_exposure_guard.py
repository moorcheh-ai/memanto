"""
Tests for the default-deployment exposure guard (#1852).

MEMANTO ships binding 0.0.0.0 over plain HTTP with no built-in TLS. The guard
must warn operators when a non-loopback bind would expose the server on the
network, and hard-fail when MEMANTO_REQUIRE_SECURE is set.
"""

import logging

import pytest

from memanto.app.config import (
    check_secure_deployment,
    is_loopback_host,
    plain_http_exposure_message,
    settings,
)


class TestSecurityDefaults:
    """New security settings default to the safe posture."""

    def test_settings_defaults(self):
        assert settings.MEMANTO_ENABLE_DOCS is False
        assert settings.MEMANTO_REQUIRE_SECURE is False


class TestIsLoopbackHost:
    def test_loopback_hosts_are_loopback(self):
        for host in ("127.0.0.1", "localhost", "::1", "LOCALHOST", "[::1]"):
            assert is_loopback_host(host) is True, host

    def test_non_loopback_hosts_are_not_loopback(self):
        for host in ("0.0.0.0", "::", "192.168.1.15", "10.0.0.2", ""):
            assert is_loopback_host(host) is False, host

    def test_none_is_not_loopback(self):
        assert is_loopback_host(None) is False


class TestPlainHttpExposureMessage:
    def test_loopback_is_safe(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        assert plain_http_exposure_message("127.0.0.1") is None
        assert plain_http_exposure_message("localhost") is None

    def test_wildcard_bind_is_exposed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        message = plain_http_exposure_message("0.0.0.0")
        assert message is not None
        assert "session cookie" in message

    def test_lan_bind_is_exposed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        assert plain_http_exposure_message("192.168.1.15") is not None

    def test_debug_mode_suppresses_warning(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", True)
        assert plain_http_exposure_message("0.0.0.0") is None


class TestCheckSecureDeployment:
    def test_loopback_is_noop(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        with caplog.at_level(logging.WARNING, logger="memanto.app.config"):
            check_secure_deployment("127.0.0.1")
        assert caplog.text == ""

    def test_exposed_bind_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        with caplog.at_level(logging.WARNING, logger="memanto.app.config"):
            check_secure_deployment("0.0.0.0")
        assert "plain HTTP" in caplog.text

    def test_exposed_bind_respects_debug(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        with caplog.at_level(logging.WARNING, logger="memanto.app.config"):
            check_secure_deployment("0.0.0.0")
        assert caplog.text == ""

    def test_require_secure_hard_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        with pytest.raises(RuntimeError, match="MEMANTO_REQUIRE_SECURE"):
            check_secure_deployment("0.0.0.0")

    def test_require_secure_loopback_still_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        check_secure_deployment("127.0.0.1")  # must not raise

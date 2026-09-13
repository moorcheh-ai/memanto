"""
Tests for the default-deployment exposure guard (#1852).

MEMANTO ships binding 0.0.0.0 over plain HTTP with no built-in TLS. The guard
must warn operators when a non-loopback bind would expose the server on the
network, and hard-fail when MEMANTO_REQUIRE_SECURE is set.
"""

import importlib
import logging
from unittest.mock import patch

import pytest
import typer
from fastapi.testclient import TestClient

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
        assert settings.MEMANTO_PROXY_ALLOWED_IPS == ""
        assert settings.proxy_allowed_ips == []


class TestIsLoopbackHost:
    def test_loopback_hosts_are_loopback(self):
        for host in (
            "127.0.0.1",
            "127.0.0.2",
            "127.254.1.1",
            "localhost",
            "::1",
            "[::1]",
            "[127.0.0.2]",
            "::ffff:127.0.0.1",
            "::ffff:127.0.0.2",
            "LOCALHOST",
        ):
            assert is_loopback_host(host) is True, host

    def test_non_loopback_hosts_are_not_loopback(self):
        for host in (
            "0.0.0.0",
            "::",
            "192.168.1.15",
            "10.0.0.2",
            "::ffff:10.0.0.1",
            "memanto",
            "",
        ):
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

    def test_any_loopback_range_is_safe(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        assert plain_http_exposure_message("127.0.0.2") is None

    def test_debug_does_not_suppress_message(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", True)
        assert plain_http_exposure_message("0.0.0.0") is not None


class TestCheckSecureDeployment:
    def test_loopback_is_noop(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        with caplog.at_level(logging.WARNING, logger="memanto.app.config"):
            check_secure_deployment("127.0.0.1")
        assert caplog.text == ""

    def test_loopback_range_is_noop(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        with caplog.at_level(logging.WARNING, logger="memanto.app.config"):
            check_secure_deployment("127.0.0.2")
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

    def test_require_secure_not_bypassed_by_debug(self, monkeypatch):
        """DEBUG suppresses the warning only, never the enforcement."""
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        with pytest.raises(RuntimeError, match="MEMANTO_REQUIRE_SECURE"):
            check_secure_deployment("0.0.0.0")

    def test_require_secure_loopback_still_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        check_secure_deployment("127.0.0.1")  # must not raise

    def test_require_secure_allows_trusted_proxy_wildcard(self, monkeypatch):
        """REQUIRE_SECURE may not block a TLS-proxy-fronted deployment.

        The __main__ entrypoint and the Docker pre-start check both call
        check_secure_deployment('0.0.0.0') directly, so this guards those
        launch paths too.
        """
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "10.0.0.5")
        check_secure_deployment("0.0.0.0")  # must not raise

    def test_require_secure_allows_trusted_proxy_lan(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", '["10.0.0.5"]')
        check_secure_deployment("192.168.1.15")  # must not raise

    def test_require_secure_still_fails_without_proxy(self, monkeypatch):
        """Empty allowlist keeps the hard failure even when REQUIRE_SECURE is on."""
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "")
        with pytest.raises(RuntimeError, match="MEMANTO_REQUIRE_SECURE"):
            check_secure_deployment("0.0.0.0")


class TestRequireSecureRequestEnforcement:
    """MEMANTO_REQUIRE_SECURE also blocks plain HTTP on the app entrypoint.

    Direct launches (`uvicorn memanto.app.main:app`) skip the startup guard, so
    the ASGI middleware must reject plain-HTTP requests as well.
    """

    @pytest.fixture
    def secure_app(self, monkeypatch):
        import memanto.app.main as main

        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        importlib.reload(main)
        yield main
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        importlib.reload(main)

    def test_plain_http_blocked_when_require_secure(self, secure_app):
        main = secure_app
        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            with TestClient(main.app) as client:
                assert client.get("/").status_code == 403

    def test_plain_http_allowed_when_secure_mode_off(self, monkeypatch):
        import memanto.app.main as main

        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        importlib.reload(main)
        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            with TestClient(main.app) as client:
                assert client.get("/").status_code == 200


class TestNotifyExposedDeployment:
    """CLI mirror of check_secure_deployment: DEBUG must not bypass REQUIRE_SECURE."""

    @staticmethod
    def _notify():
        from memanto.cli.commands.core import _notify_exposed_deployment

        return _notify_exposed_deployment

    def test_loopback_is_silent(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        called: dict[str, bool] = {"warn": False}

        import memanto.cli.commands.core as core

        def recorder(message: str) -> None:
            called["warn"] = True

        monkeypatch.setattr(core, "_warn", recorder)
        self._notify()("127.0.0.1")
        assert called["warn"] is False

    def test_require_secure_fails_even_in_debug(self, monkeypatch):
        """The exact CodeRabbit finding: DEBUG must not mute the hard failure."""
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)

        import memanto.cli.commands.core as core

        def fail(message: str) -> None:
            raise typer.Exit(1)

        monkeypatch.setattr(core, "_error", fail)
        with pytest.raises(typer.Exit):
            self._notify()("0.0.0.0")

    def test_require_secure_allows_trusted_proxy(self, monkeypatch):
        """serve/ui may start when a TLS-terminating proxy is allowlisted."""
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", True)
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "10.0.0.5")
        called: dict[str, bool] = {"error": False}

        import memanto.cli.commands.core as core

        def recorder(message: str) -> None:
            called["error"] = True

        monkeypatch.setattr(core, "_error", recorder)
        self._notify()("0.0.0.0")
        assert called["error"] is False

    def test_warning_kept_for_exposed_bind_without_proxy(self, monkeypatch):
        """Without an allowlist the shared message logic still reports exposure."""
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", "")
        called: dict[str, bool] = {"warn": False}

        import memanto.cli.commands.core as core

        def recorder(message: str) -> None:
            called["warn"] = True

        monkeypatch.setattr(core, "_warn", recorder)
        self._notify()("192.168.1.15")
        assert called["warn"] is True

    def test_debug_suppresses_warning_only(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        called: dict[str, bool] = {"warn": False}

        import memanto.cli.commands.core as core

        def recorder(message: str) -> None:
            called["warn"] = True

        monkeypatch.setattr(core, "_warn", recorder)
        self._notify()("0.0.0.0")
        assert called["warn"] is False

    def test_exposed_bind_warns_in_normal_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "MEMANTO_REQUIRE_SECURE", False)
        called: dict[str, bool] = {"warn": False}

        import memanto.cli.commands.core as core

        def recorder(message: str) -> None:
            called["warn"] = True

        monkeypatch.setattr(core, "_warn", recorder)
        self._notify()("192.168.1.15")
        assert called["warn"] is True

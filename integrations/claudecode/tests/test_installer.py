"""Tests for the compatibility wrapper around the core connection engine."""

from __future__ import annotations

from claudecode_memanto import installer


def test_install_delegates_to_core_connect(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        installer,
        "install_agent",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"errors": []},
    )

    assert installer.install_hooks(global_scope=True) == 0
    assert calls == [(("claude-code",), {"is_global": True})]


def test_uninstall_returns_failure_for_core_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        installer, "remove_agent", lambda *args, **kwargs: {"errors": ["failed"]}
    )

    assert installer.uninstall_hooks() == 1

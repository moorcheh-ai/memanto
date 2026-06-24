"""Tests for the settings.json hook installer (idempotency + hook preservation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memanto_skills import installer

_EVENTS = ("SessionStart", "UserPromptExpansion", "Stop")


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the installer against an isolated project directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".claude" / "settings.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _managed_count(settings: dict) -> int:
    return sum(
        1
        for entries in settings.get("hooks", {}).values()
        for entry in entries
        for hook in entry.get("hooks", [])
        if installer._MARKER in str(hook.get("command", ""))
    )


def test_install_registers_all_three_events(settings_path: Path) -> None:
    assert installer.install_hooks() == 0
    settings = _load(settings_path)
    for event in _EVENTS:
        assert event in settings["hooks"], f"missing {event}"
    assert _managed_count(settings) == 3


def test_reinstall_is_idempotent(settings_path: Path) -> None:
    installer.install_hooks()
    installer.install_hooks()
    assert _managed_count(_load(settings_path)) == 3  # no duplicates


def test_install_preserves_existing_user_hooks(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    user_hook = {"type": "command", "command": "echo user-hook"}
    settings_path.write_text(
        json.dumps({"hooks": {"UserPromptExpansion": [{"hooks": [user_hook]}]}}),
        encoding="utf-8",
    )

    installer.install_hooks()

    entries = _load(settings_path)["hooks"]["UserPromptExpansion"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert "echo user-hook" in commands
    assert any(installer._MARKER in c for c in commands)


def test_strip_preserves_user_hook_inside_mixed_entry(settings_path: Path) -> None:
    """A user hook merged into one of our entries must survive a re-install."""
    installer.install_hooks()
    settings = _load(settings_path)
    user_hook = {"type": "command", "command": "echo merged-by-user"}
    settings["hooks"]["Stop"][0]["hooks"].append(user_hook)
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    installer.install_hooks()

    entries = _load(settings_path)["hooks"]["Stop"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert "echo merged-by-user" in commands
    assert sum(installer._MARKER in c for c in commands) == 1  # ours, once


def test_uninstall_removes_only_managed_hooks(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    user_hook = {"type": "command", "command": "echo keep-me"}
    settings_path.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [user_hook]}]}}),
        encoding="utf-8",
    )
    installer.install_hooks()

    assert installer.uninstall_hooks() == 0

    settings = _load(settings_path)
    assert _managed_count(settings) == 0
    commands = [h["command"] for e in settings["hooks"]["Stop"] for h in e["hooks"]]
    assert commands == ["echo keep-me"]


def test_uninstall_when_nothing_installed_is_a_noop(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    original = json.dumps({"hooks": {}})
    settings_path.write_text(original, encoding="utf-8")

    assert installer.uninstall_hooks() == 0
    # File untouched (no rewrite, no backup churn) when there was nothing to remove.
    assert settings_path.read_text(encoding="utf-8") == original


def test_install_recovers_from_malformed_hooks_field(settings_path: Path) -> None:
    """A hand-edited settings.json with ``hooks`` as a list must not crash."""
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"hooks": ["not", "a", "dict"]}), encoding="utf-8"
    )

    assert installer.install_hooks() == 0
    settings = _load(settings_path)
    assert isinstance(settings["hooks"], dict)
    assert _managed_count(settings) == 3


def test_uninstall_recovers_from_malformed_hooks_field(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"hooks": "totally wrong"}), encoding="utf-8")
    assert installer.uninstall_hooks() == 0

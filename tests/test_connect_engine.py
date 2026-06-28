"""Regression tests for AI-agent connect engine state file handling."""

from __future__ import annotations

import json
from pathlib import Path

from memanto.cli.connect.agent_registry import AGENT_REGISTRY
from memanto.cli.connect.engine import _install_hooks, _install_permissions


def _load_json(path: Path) -> dict:
    """Load a settings file and assert the repair path wrote an object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_install_hooks_recovers_from_non_object_settings(tmp_path: Path) -> None:
    """A hand-edited Claude settings file must not block hook setup."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    result = _install_hooks(AGENT_REGISTRY["claude-code"], tmp_path, False)

    assert result == "Added SessionStart hook"
    settings = _load_json(settings_path)
    session_start = settings["hooks"]["SessionStart"]
    assert isinstance(session_start, list)
    assert any(
        "memanto memory sync" in hook["command"]
        for group in session_start
        for hook in group["hooks"]
    )


def test_install_hooks_recovers_from_malformed_hook_containers(
    tmp_path: Path,
) -> None:
    """Malformed nested hook containers should be replaced, not crash."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"hooks": {"SessionStart": "not-a-list"}}),
        encoding="utf-8",
    )

    result = _install_hooks(AGENT_REGISTRY["claude-code"], tmp_path, False)

    assert result == "Added SessionStart hook"
    settings = _load_json(settings_path)
    assert isinstance(settings["hooks"]["SessionStart"], list)


def test_install_permissions_recovers_from_malformed_permission_containers(
    tmp_path: Path,
) -> None:
    """A malformed permissions shape should not prevent MEMANTO permission setup."""
    permissions_path = tmp_path / ".claude" / "settings.local.json"
    permissions_path.parent.mkdir(parents=True)
    permissions_path.write_text(
        json.dumps({"permissions": {"allow": "not-a-list"}}),
        encoding="utf-8",
    )

    result = _install_permissions(AGENT_REGISTRY["claude-code"], tmp_path, False)

    assert result == "Added permissions"
    settings = _load_json(permissions_path)
    assert settings["permissions"]["allow"] == ["Bash(memanto:*)"]

"""Tests for the claudecode-memanto CLI."""

from __future__ import annotations

import json
from pathlib import Path

from memanto.cli.connect import engine, mcp_setup

from claudecode_memanto import cli


def test_cli_install_passes_project_global_and_agent_id(monkeypatch, capsys) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_install(*args: object, **kwargs: object) -> dict[str, list[str]]:
        calls.append((args, kwargs))
        return {"steps": ["Added memanto MCP server to .mcp.json"], "errors": []}

    monkeypatch.setattr(cli, "install_agent", fake_install)

    exit_code = cli.main(
        ["install", "--project-dir", "./my-proj", "--agent-id", "claude-agent"]
    )

    assert exit_code == 0
    assert calls == [
        (
            ("claude-code",),
            {
                "project_dir": "./my-proj",
                "is_global": False,
                "mcp_agent_id": "claude-agent",
            },
        )
    ]
    assert "Added memanto MCP server to .mcp.json" in capsys.readouterr().out


def test_cli_uninstall_passes_project_and_global(monkeypatch, capsys) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_remove(*args: object, **kwargs: object) -> dict[str, list[str]]:
        calls.append((args, kwargs))
        return {"steps": ["Removed memanto MCP server from .claude.json"], "errors": []}

    monkeypatch.setattr(cli, "remove_agent", fake_remove)

    exit_code = cli.main(["uninstall", "-g", "-p", "./my-proj"])

    assert exit_code == 0
    assert calls == [
        (
            ("claude-code",),
            {"project_dir": "./my-proj", "is_global": True},
        )
    ]
    assert "Removed memanto MCP server from .claude.json" in capsys.readouterr().out


def test_cli_returns_nonzero_on_errors(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "install_agent",
        lambda *args, **kwargs: {"steps": [], "errors": ["failed"]},
    )

    assert cli.main(["install"]) == 1
    assert "error: failed" in capsys.readouterr().out


def test_cli_end_to_end_mcp_install_and_uninstall(tmp_path: Path, monkeypatch) -> None:
    class StubConfigManager:
        def add_connection(self, *args, **kwargs):
            return None

        def remove_connection(self, *args, **kwargs):
            return None

        def get_active_session(self):
            return ("default-agent", "token")

    monkeypatch.setattr(engine, "ConfigManager", StubConfigManager)
    monkeypatch.setattr(mcp_setup.shutil, "which", lambda name: "/bin/memanto-mcp")

    project = tmp_path / "demo_project"
    project.mkdir()

    rc_install = cli.main(
        ["install", "--project-dir", str(project), "--agent-id", "test-claude-agent"]
    )
    assert rc_install == 0

    mcp_config = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp_config["mcpServers"]["memanto"]
    assert server["command"] == str(Path("/bin/memanto-mcp").resolve())
    assert server["env"]["MEMANTO_DEFAULT_AGENT_ID"] == "test-claude-agent"
    assert server["env"]["MEMANTO_DEFAULT_SOURCE"] == "claude"
    assert server["env"]["MEMANTO_MANAGED_BY"] == "memanto-connect"

    local_settings = json.loads(
        (project / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert "memanto" in local_settings["enabledMcpjsonServers"]
    assert "mcp__memanto" in local_settings["permissions"]["allow"]

    settings = json.loads(
        (project / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    post_tool_matchers = [
        group.get("matcher") for group in settings["hooks"]["PostToolUse"]
    ]
    assert "mcp__memanto__.*" in post_tool_matchers

    claude_md = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "use the `memanto` MCP tools" in claude_md
    assert "--source test-claude-agent" in claude_md

    rc_uninstall = cli.main(["uninstall", "--project-dir", str(project)])
    assert rc_uninstall == 0
    assert not (project / "CLAUDE.md").exists()
    assert not (project / ".mcp.json").exists()
    assert not (project / ".claude" / "settings.json").exists()
    assert not (project / ".claude" / "settings.local.json").exists()


def test_cli_global_install_uses_user_settings_json(
    tmp_path: Path, monkeypatch
) -> None:
    class StubConfigManager:
        def add_connection(self, *args: object, **kwargs: object) -> None:
            return None

        def remove_connection(self, *args: object, **kwargs: object) -> None:
            return None

        def get_active_session(self) -> tuple[str, str]:
            return ("default-agent", "token")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(engine, "ConfigManager", StubConfigManager)
    monkeypatch.setattr(mcp_setup.shutil, "which", lambda name: "/bin/memanto-mcp")

    assert cli.main(["install", "--global", "--agent-id", "global-agent"]) == 0

    user_settings = json.loads(
        (home / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "mcp__memanto" in user_settings["permissions"]["allow"]
    assert "hooks" in user_settings
    assert not (home / ".claude" / "settings.local.json").exists()

    assert cli.main(["uninstall", "--global"]) == 0
    assert not (home / ".claude" / "settings.json").exists()
    assert not (home / ".claude.json").exists()

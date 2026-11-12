"""Tests for the kimicode-memanto CLI and compatibility wrapper."""

from __future__ import annotations

import json
from pathlib import Path

from memanto.cli.connect import engine, mcp_setup

from kimicode_memanto import cli, installer


def test_install_delegates_to_core_connect(monkeypatch) -> None:
    """Verify installer.install_hooks delegates to install_agent."""
    calls = []
    monkeypatch.setattr(
        installer,
        "install_agent",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"errors": []},
    )

    assert installer.install_hooks(global_scope=True) == 0
    assert calls == [(("kimi-code",), {"is_global": True})]


def test_uninstall_returns_failure_for_core_errors(monkeypatch) -> None:
    """Verify installer.uninstall_hooks returns 1 when remove_agent reports errors."""
    monkeypatch.setattr(
        installer, "remove_agent", lambda *args, **kwargs: {"errors": ["failed"]}
    )

    assert installer.uninstall_hooks() == 1


def test_cli_install_passes_project_global_and_agent_id(monkeypatch, capsys) -> None:
    """Verify CLI install passes project_dir, is_global, and mcp_agent_id."""
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_install(*args: object, **kwargs: object) -> dict[str, list[str]]:
        calls.append((args, kwargs))
        return {"steps": ["Added memanto MCP server to mcp.json"], "errors": []}

    monkeypatch.setattr(cli, "install_agent", fake_install)

    exit_code = cli.main(
        ["install", "--project-dir", "./my-proj", "--agent-id", "kimi-agent"]
    )

    assert exit_code == 0
    assert calls == [
        (
            ("kimi-code",),
            {
                "project_dir": "./my-proj",
                "is_global": False,
                "mcp_agent_id": "kimi-agent",
            },
        )
    ]
    assert "Added memanto MCP server to mcp.json" in capsys.readouterr().out


def test_cli_uninstall_passes_project_and_global(monkeypatch, capsys) -> None:
    """Verify CLI uninstall passes project_dir and is_global."""
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_remove(*args: object, **kwargs: object) -> dict[str, list[str]]:
        calls.append((args, kwargs))
        return {"steps": ["Removed memanto MCP server from mcp.json"], "errors": []}

    monkeypatch.setattr(cli, "remove_agent", fake_remove)

    exit_code = cli.main(["uninstall", "-g", "-p", "./my-proj"])

    assert exit_code == 0
    assert calls == [
        (
            ("kimi-code",),
            {"project_dir": "./my-proj", "is_global": True},
        )
    ]
    assert "Removed memanto MCP server from mcp.json" in capsys.readouterr().out


def test_cli_returns_nonzero_on_errors(monkeypatch, capsys) -> None:
    """Verify CLI returns exit code 1 and prints errors when installation fails."""
    monkeypatch.setattr(
        cli,
        "install_agent",
        lambda *args, **kwargs: {"steps": [], "errors": ["failed"]},
    )

    assert cli.main(["install"]) == 1
    assert "error: failed" in capsys.readouterr().out


def test_cli_end_to_end_mcp_install_and_uninstall(tmp_path: Path, monkeypatch) -> None:
    """Verify end-to-end project install and uninstall with MCP and TOML hooks."""

    class StubConfigManager:
        def add_connection(self, *args, **kwargs):
            return None

        def remove_connection(self, *args, **kwargs):
            return None

        def get_active_session(self):
            return ("default-agent", "token")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(engine, "ConfigManager", StubConfigManager)
    monkeypatch.setattr(mcp_setup.shutil, "which", lambda name: "/bin/memanto-mcp")

    project = tmp_path / "demo_project"
    project.mkdir()

    rc_install = cli.main(
        ["install", "--project-dir", str(project), "--agent-id", "test-kimi-agent"]
    )
    assert rc_install == 0

    mcp_config = json.loads(
        (project / ".kimi-code" / "mcp.json").read_text(encoding="utf-8")
    )
    server = mcp_config["mcpServers"]["memanto"]
    assert server["command"] == str(Path("/bin/memanto-mcp").resolve())
    assert server["env"]["MEMANTO_DEFAULT_AGENT_ID"] == "test-kimi-agent"
    assert server["env"]["MEMANTO_DEFAULT_SOURCE"] == "kimi-code"
    assert server["env"]["MEMANTO_MANAGED_BY"] == "memanto-connect"

    config_toml = (home / ".kimi-code" / "config.toml").read_text(encoding="utf-8")
    assert engine.TOML_HOOK_SENTINEL in config_toml
    assert 'matcher = "mcp__memanto__.*"' in config_toml

    agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "use the `memanto` MCP tools" in agents_md
    assert "--source test-kimi-agent" in agents_md

    rc_uninstall = cli.main(["uninstall", "--project-dir", str(project)])
    assert rc_uninstall == 0
    assert not (project / "AGENTS.md").exists()
    assert not (project / ".kimi-code" / "mcp.json").exists()
    assert engine.TOML_HOOK_SENTINEL not in (
        home / ".kimi-code" / "config.toml"
    ).read_text(encoding="utf-8")

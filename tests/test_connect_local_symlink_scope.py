"""Local connect writes must stay inside the selected project root."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from memanto.cli.config.manager import ConfigManager
from memanto.cli.connect import engine
from memanto.cli.connect.agent_registry import get_agent
from memanto.cli.connect.path_scope import assert_project_local_path


def _claude_fixture(tmp_path: Path, filename: str):
    home = tmp_path / "home"
    project = home / "repo"
    (project / ".claude").mkdir(parents=True)
    (home / ".claude").mkdir()
    victim = home / ".claude" / "settings.json"
    victim.write_text('{"theme":"dark"}\n', encoding="utf-8")
    (project / ".claude" / filename).symlink_to(victim)
    return project, victim


def test_assert_project_local_path_rejects_escape(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n", encoding="utf-8")
    alias = project / "alias.txt"
    alias.symlink_to(outside)
    with pytest.raises(ValueError, match="outside project"):
        assert_project_local_path(project, alias, action="local write")


def test_local_permissions_reject_out_of_project_symlink(tmp_path: Path):
    agent = get_agent("claude-code")
    assert agent is not None
    project, victim = _claude_fixture(tmp_path, agent.permissions_file)
    before = victim.read_bytes()
    with pytest.raises(ValueError, match="outside project"):
        engine._install_permissions(agent, project, is_global=False)
    assert victim.read_bytes() == before


def test_local_hooks_reject_out_of_project_symlink(tmp_path: Path):
    agent = get_agent("claude-code")
    assert agent is not None
    project, victim = _claude_fixture(tmp_path, agent.hook_config.settings_file)
    before = victim.read_bytes()
    with pytest.raises(ValueError, match="outside project"):
        engine._install_hooks(agent, project, is_global=False)
    assert victim.read_bytes() == before


def test_normal_local_claude_paths_still_work(tmp_path: Path):
    agent = get_agent("claude-code")
    assert agent is not None
    project = tmp_path / "repo"
    project.mkdir()
    assert engine._install_permissions(agent, project, False) == "Added permissions"
    # Hooks may return None when hook assets are unavailable in the test env;
    # permissions proves the happy-path scope check still allows in-project writes.
    perm = project / ".claude" / agent.permissions_file
    assert perm.is_file()
    assert not perm.is_symlink()


def test_skill_parent_symlink_rejected_before_directory_creation(tmp_path: Path):
    agent = get_agent("claude-code")
    assert agent is not None
    home = tmp_path / "home"
    project = home / "repo"
    outside = home / "outside-skills"
    project.mkdir(parents=True)
    outside.mkdir()
    (project / ".claude").mkdir()
    (project / ".claude" / "skills").symlink_to(outside)
    with pytest.raises(ValueError, match="outside project"):
        engine._install_skill(agent, project, is_global=False)
    assert not (outside / "memanto").exists()


def test_parent_directory_symlink_escape_rejected(tmp_path: Path):
    agent = get_agent("claude-code")
    assert agent is not None
    home = tmp_path / "home"
    project = home / "repo"
    project.mkdir(parents=True)
    (home / ".claude").mkdir()
    (project / ".claude").symlink_to(home / ".claude")
    with pytest.raises(ValueError, match="outside project"):
        engine._install_permissions(agent, project, is_global=False)


@pytest.mark.parametrize(
    ("agent_name", "relative_path", "content"),
    [
        ("github-copilot", ".github/copilot-instructions.md", "# Project notes\n"),
        ("cursor", ".cursor/rules/memanto.mdc", "# Project notes\n"),
        ("github-copilot", ".agents/skills/memanto/SKILL.md", "Original skill\n"),
        ("claude-code", ".claude/settings.json", '{"theme":"dark"}\n'),
        ("claude-code", ".claude/settings.local.json", '{"theme":"dark"}\n'),
        ("pi", ".pi/extensions/memanto-sync.ts", "// Existing extension\n"),
    ],
)
def test_local_install_does_not_write_through_hardlink(
    tmp_path: Path, monkeypatch, agent_name: str, relative_path: str, content: str
):
    project = tmp_path / "project"
    target = project / relative_path
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text(content, encoding="utf-8")
    outside.chmod(0o640)
    os.link(outside, target)
    before = outside.read_bytes()
    config = ConfigManager(tmp_path / "config")
    monkeypatch.setattr(engine, "ConfigManager", lambda: config)

    result = engine.install_agent(agent_name, str(project), is_global=False)

    assert result["errors"] == []
    assert outside.read_bytes() == before
    assert target.read_bytes() != before
    assert not os.path.samefile(target, outside)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize(
    ("agent_name", "relative_path", "content"),
    [
        ("github-copilot", ".github/copilot-instructions.md", "# Project notes\n"),
        ("claude-code", ".claude/settings.json", '{"theme":"dark"}\n'),
        ("claude-code", ".claude/settings.local.json", '{"theme":"dark"}\n'),
    ],
)
def test_local_remove_does_not_write_through_hardlink(
    tmp_path: Path, monkeypatch, agent_name: str, relative_path: str, content: str
):
    project = tmp_path / "project"
    target = project / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(content, encoding="utf-8")
    target.chmod(0o640)
    config = ConfigManager(tmp_path / "config")
    monkeypatch.setattr(engine, "ConfigManager", lambda: config)
    assert engine.install_agent(agent_name, str(project), False)["errors"] == []
    outside = tmp_path / "outside"
    os.link(target, outside)
    before = outside.read_bytes()

    result = engine.remove_agent(agent_name, str(project), is_global=False)

    assert result["errors"] == []
    assert outside.read_bytes() == before
    assert target.read_bytes() != before
    assert not os.path.samefile(target, outside)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_local_install_preserves_in_project_symlink_and_mode(
    tmp_path: Path, monkeypatch
):
    project = tmp_path / "project"
    (project / ".github").mkdir(parents=True)
    target = project / "shared.md"
    target.write_text("# Project notes\n", encoding="utf-8")
    target.chmod(0o640)
    alias = project / ".github/copilot-instructions.md"
    alias.symlink_to(target)
    config = ConfigManager(tmp_path / "config")
    monkeypatch.setattr(engine, "ConfigManager", lambda: config)

    result = engine.install_agent("github-copilot", str(project), False)

    assert result["errors"] == []
    assert alias.is_symlink()
    assert engine.MEMANTO_SENTINEL in target.read_text(encoding="utf-8")
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    # A new integration file retains ordinary file creation permissions.
    ordinary = project / "ordinary.txt"
    ordinary.write_text("ordinary\n", encoding="utf-8")
    skill = project / ".agents/skills/memanto/SKILL.md"
    assert stat.S_IMODE(skill.stat().st_mode) == stat.S_IMODE(ordinary.stat().st_mode)


def test_local_install_refuses_hardlink_created_before_exclusive_open(
    tmp_path: Path, monkeypatch
):
    project = tmp_path / "project"
    (project / ".github").mkdir(parents=True)
    target = project / ".github/copilot-instructions.md"
    outside = tmp_path / "outside"
    outside.write_text("Keep outside unchanged.\n", encoding="utf-8")
    before = outside.read_bytes()
    config = ConfigManager(tmp_path / "config")
    monkeypatch.setattr(engine, "ConfigManager", lambda: config)
    original_open = Path.open

    def raced_open(path, mode="r", *args, **kwargs):
        if path == target and mode == "x":
            os.link(outside, target)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    result = engine.install_agent("github-copilot", str(project), False)

    assert any("Instruction file:" in error for error in result["errors"])
    assert outside.read_bytes() == before
    assert os.path.samefile(target, outside)

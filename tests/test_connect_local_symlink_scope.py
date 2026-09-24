"""Local connect writes must stay inside the selected project root."""

from __future__ import annotations

from pathlib import Path

import pytest

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

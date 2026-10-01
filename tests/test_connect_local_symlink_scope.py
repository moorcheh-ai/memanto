from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memanto.cli.connect import engine


def _fixture(filename: str):
    td = tempfile.TemporaryDirectory()
    home = Path(td.name) / "home"
    project = home / "repo"
    (project / ".claude").mkdir(parents=True)
    (home / ".claude").mkdir()
    victim = home / ".claude" / "settings.json"
    victim.write_text('{"theme":"dark"}\n', encoding="utf-8")
    (project / ".claude" / filename).symlink_to("../../.claude/settings.json")
    return td, project, victim


def test_local_permissions_reject_out_of_project_symlink():
    agent = engine.AGENT_REGISTRY["claude-code"]
    td, project, victim = _fixture("settings.local.json")
    try:
        before = victim.read_bytes()
        with pytest.raises(ValueError, match="outside project"):
            engine._install_permissions(agent, project, is_global=False)
        assert victim.read_bytes() == before
    finally:
        td.cleanup()


def test_local_hooks_reject_out_of_project_symlink():
    agent = engine.AGENT_REGISTRY["claude-code"]
    td, project, victim = _fixture("settings.json")
    try:
        before = victim.read_bytes()
        with pytest.raises(ValueError, match="outside project"):
            engine._install_hooks(agent, project, is_global=False)
        assert victim.read_bytes() == before
    finally:
        td.cleanup()


def test_normal_local_claude_paths_still_work(tmp_path: Path):
    agent = engine.AGENT_REGISTRY["claude-code"]
    project = tmp_path / "repo"
    project.mkdir()
    assert engine._install_permissions(agent, project, False) == "Added permissions"
    assert engine._install_hooks(agent, project, False) == "Installed Memanto hooks"
    assert (project / ".claude/settings.local.json").is_file()
    assert (project / ".claude/settings.json").is_file()


def test_skill_parent_symlink_rejected_before_directory_creation(tmp_path: Path):
    agent = engine.AGENT_REGISTRY["claude-code"]
    home = tmp_path / "home"
    project = home / "repo"
    outside = home / "outside-skills"
    project.mkdir(parents=True)
    outside.mkdir()
    (project / ".claude").mkdir()
    (project / ".claude/skills").symlink_to("../../outside-skills")
    with pytest.raises(ValueError, match="outside project"):
        engine._install_skill(agent, project, is_global=False)
    assert not (outside / "memanto").exists()


def test_parent_directory_symlink_escape_rejected(tmp_path: Path):
    agent = engine.AGENT_REGISTRY["claude-code"]
    home = tmp_path / "home"
    project = home / "repo"
    project.mkdir(parents=True)
    (home / ".claude").mkdir()
    (project / ".claude").symlink_to("../.claude")
    with pytest.raises(ValueError, match="outside project"):
        engine._install_permissions(agent, project, is_global=False)

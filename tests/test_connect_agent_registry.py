from pathlib import Path

import pytest

from memanto.cli.connect.agent_registry import AGENT_REGISTRY


@pytest.mark.parametrize(
    ("agent_name", "expected_path"),
    [
        ("cursor", ".cursor/rules/memanto.mdc"),
        ("continue", ".continue/rules/memanto.md"),
        ("roo", ".roo/rules/memanto.md"),
        ("augment", ".augment/rules/memanto.md"),
    ],
)
def test_global_instruction_path_does_not_repeat_config_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    agent_name: str,
    expected_path: str,
) -> None:
    """Resolve nested global instructions without repeating their config root."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    resolved = AGENT_REGISTRY[agent_name].resolve_instruction_file(
        tmp_path / "project", is_global=True
    )

    assert resolved == tmp_path / expected_path


@pytest.mark.parametrize(
    ("agent_name", "expected_path"),
    [
        ("claude-code", ".claude/CLAUDE.md"),
        ("windsurf", ".codeium/windsurf/.windsurfrules"),
        ("cline", ".clinerules/memanto.md"),
    ],
)
def test_global_instruction_path_keeps_unprefixed_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    agent_name: str,
    expected_path: str,
) -> None:
    """Keep global instruction files that are not nested under local config."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    resolved = AGENT_REGISTRY[agent_name].resolve_instruction_file(
        tmp_path / "project", is_global=True
    )

    assert resolved == tmp_path / expected_path


def test_local_instruction_path_is_unchanged(tmp_path: Path) -> None:
    """Keep project-local instruction resolution unchanged."""
    resolved = AGENT_REGISTRY["cursor"].resolve_instruction_file(
        tmp_path, is_global=False
    )

    assert resolved == tmp_path / ".cursor/rules/memanto.mdc"

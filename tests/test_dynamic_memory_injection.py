from pathlib import Path
from unittest.mock import patch

from memanto.cli.connect.updater import inject_dynamic_memories

SENTINEL_START = "<!-- MEMANTO-DYNAMIC-MEMORIES -->"
SENTINEL_END = "<!-- /MEMANTO-DYNAMIC-MEMORIES -->"


def _instruction_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"before\n{SENTINEL_START}\nold\n{SENTINEL_END}\nafter\n")


def test_manual_sync_uses_the_single_local_connection(tmp_path):
    instruction_path = tmp_path / ".github" / "copilot-instructions.md"
    _instruction_file(instruction_path)
    connections = {
        "github-copilot": {
            "projects": [str(tmp_path.resolve())],
            "installed_global": False,
        }
    }

    with patch(
        "memanto.cli.config.manager.ConfigManager.load_connections",
        return_value=connections,
    ):
        inject_dynamic_memories(str(tmp_path), "- [INSTRUCTION] C:\\Users\\rule")

    content = instruction_path.read_text()
    assert "- [INSTRUCTION] C:\\Users\\rule" in content
    assert "old" not in content


def test_global_scope_never_updates_the_local_instruction(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    global_instruction = home / ".claude" / "CLAUDE.md"
    _instruction_file(global_instruction)
    local_instruction = tmp_path / "CLAUDE.md"
    _instruction_file(local_instruction)
    connections = {"claude-code": {"projects": [], "installed_global": True}}

    with patch(
        "memanto.cli.config.manager.ConfigManager.load_connections",
        return_value=connections,
    ):
        inject_dynamic_memories(
            str(tmp_path),
            "- [INSTRUCTION] Global rule",
            connection="claude-code",
            scope="global",
        )

    assert "Global rule" in global_instruction.read_text()
    assert "old" in local_instruction.read_text()


def test_sync_updates_all_local_connections(tmp_path):
    copilot_path = tmp_path / ".github" / "copilot-instructions.md"
    _instruction_file(copilot_path)
    claude_path = tmp_path / "CLAUDE.md"
    _instruction_file(claude_path)

    connections = {
        "github-copilot": {
            "projects": [str(tmp_path.resolve())],
            "installed_global": False,
        },
        "claude-code": {
            "projects": [str(tmp_path.resolve())],
            "installed_global": False,
        },
    }

    with patch(
        "memanto.cli.config.manager.ConfigManager.load_connections",
        return_value=connections,
    ):
        inject_dynamic_memories(str(tmp_path), "- [INSTRUCTION] Rule")

    assert "Rule" in copilot_path.read_text()
    assert "Rule" in claude_path.read_text()

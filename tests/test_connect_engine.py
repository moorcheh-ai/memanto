import json

from memanto.cli.connect import engine
from memanto.cli.connect.agent_registry import AGENT_REGISTRY
from memanto.cli.connect.engine import _remove_instructions
from memanto.cli.connect.templates import get_instruction_content


def test_remove_dedicated_instruction_preserves_unmanaged_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text("User-owned Cursor rules\n", encoding="utf-8")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result is None
    assert rules_path.read_text(encoding="utf-8") == "User-owned Cursor rules\n"


def test_remove_dedicated_instruction_preserves_non_utf8_unmanaged_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_bytes(b"\xff\xfeuser-owned rules")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result is None
    assert rules_path.read_bytes() == b"\xff\xfeuser-owned rules"


def test_remove_dedicated_instruction_deletes_memanto_managed_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text(get_instruction_content("cursor"), encoding="utf-8")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result == "Removed memanto.mdc"
    assert not rules_path.exists()


class DummyConfigManager:
    def add_connection(self, *args, **kwargs):
        return None

    def remove_connection(self, *args, **kwargs):
        return None


def stub_config_manager(monkeypatch):
    monkeypatch.setattr(engine, "ConfigManager", DummyConfigManager)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_remove_claude_code_removes_installed_hook_and_permissions(
    tmp_path, monkeypatch
):
    stub_config_manager(monkeypatch)

    install_result = engine.install_agent("claude-code", str(tmp_path))

    assert install_result["errors"] == []
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".claude" / "settings.local.json").exists()

    remove_result = engine.remove_agent("claude-code", str(tmp_path))

    assert remove_result["errors"] == []
    assert any("Memanto hooks" in step for step in remove_result["steps"])
    assert any("permissions" in step for step in remove_result["steps"])
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".claude" / "settings.local.json").exists()


def test_remove_claude_code_preserves_unrelated_hooks_and_permissions(
    tmp_path, monkeypatch
):
    stub_config_manager(monkeypatch)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    permissions_path = claude_dir / "settings.local.json"

    settings_path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {"type": "command", "command": "echo keep"},
                                {
                                    "type": "command",
                                    "command": "memanto memory sync --project-dir .",
                                },
                                {
                                    "type": "command",
                                    "command": "memanto memory sync --project-dir .",
                                    "timeout": 30,
                                },
                            ],
                        },
                        {
                            "matcher": "manual",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "memanto memory sync --project-dir .",
                                    "timeout": 30,
                                }
                            ],
                        },
                        {"matcher": "other", "hooks": [{"command": "echo other"}]},
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    permissions_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(git status)", "Bash(memanto:*)"],
                },
                "env": {"KEEP": "1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    remove_result = engine.remove_agent("claude-code", str(tmp_path))

    assert remove_result["errors"] == []
    settings = read_json(settings_path)
    permissions = read_json(permissions_path)
    assert settings["theme"] == "dark"
    assert settings["hooks"]["SessionStart"] == [
        {"matcher": "other", "hooks": [{"command": "echo other"}]},
    ]
    assert permissions == {
        "permissions": {"allow": ["Bash(git status)"]},
        "env": {"KEEP": "1"},
    }

import json
from pathlib import Path
from unittest.mock import patch

from memanto.cli.config.manager import ConfigManager
from memanto.cli.connect import engine


def test_remove_agent_cleans_its_hook_and_permission_without_touching_user_config(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    config_dir = tmp_path / "config"
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)

    settings_path = claude_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [{"type": "command", "command": "echo user-hook"}],
                        }
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
                },
                "statusLine": {"type": "command", "command": "echo ready"},
            }
        ),
        encoding="utf-8",
    )
    permissions_path = claude_dir / "settings.local.json"
    permissions_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": ["Bash(rm:*)"],
                },
                "enabledPlugins": {"example@marketplace": True},
            }
        ),
        encoding="utf-8",
    )

    with patch.object(engine, "ConfigManager", lambda: ConfigManager(config_dir)):
        install_result = engine.install_agent("claude-code", str(project_dir))
        remove_result = engine.remove_agent("claude-code", str(project_dir))

    assert install_result["errors"] == []
    assert remove_result["errors"] == []
    assert any("SessionStart hook" in step for step in remove_result["steps"])
    assert any("permission" in step for step in remove_result["steps"])

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["hooks"] == {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [{"type": "command", "command": "echo user-hook"}],
            }
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
    }
    assert settings["statusLine"] == {"type": "command", "command": "echo ready"}

    permissions = json.loads(permissions_path.read_text(encoding="utf-8"))
    assert permissions == {
        "permissions": {
            "allow": ["Bash(git:*)"],
            "deny": ["Bash(rm:*)"],
        },
        "enabledPlugins": {"example@marketplace": True},
    }
    assert ConfigManager(config_dir).load_connections() == {}

import json

from memanto.cli.connect.agent_registry import CLAUDE_CODE
from memanto.cli.connect.engine import _install_hooks


def _session_start_commands(settings_path):
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    return [
        hook.get("command")
        for group in settings.get("hooks", {}).get("SessionStart", [])
        for hook in group.get("hooks", [])
    ]


def test_install_hooks_ignores_unrelated_memanto_commands(tmp_path):
    """A different hook mentioning memanto must not suppress the sync hook."""
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_path = settings_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo memanto diagnostics",
                                    "timeout": 5,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = _install_hooks(CLAUDE_CODE, tmp_path, is_global=False)

    assert result == "Added SessionStart hook"
    commands = _session_start_commands(settings_path)
    assert "echo memanto diagnostics" in commands
    assert "memanto memory sync --project-dir ." in commands


def test_install_hooks_is_idempotent_for_existing_sync_hook(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"

    first = _install_hooks(CLAUDE_CODE, tmp_path, is_global=False)
    second = _install_hooks(CLAUDE_CODE, tmp_path, is_global=False)

    assert first == "Added SessionStart hook"
    assert second is None
    commands = _session_start_commands(settings_path)
    assert commands.count("memanto memory sync --project-dir .") == 1

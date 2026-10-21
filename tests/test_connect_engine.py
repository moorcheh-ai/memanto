import json
from pathlib import Path

import pytest

from memanto.cli.connect import engine
from memanto.cli.connect.agent_registry import AGENT_REGISTRY
from memanto.cli.connect.engine import _remove_instructions
from memanto.cli.connect.templates import (
    MEMANTO_SENTINEL,
    MEMANTO_SENTINEL_END,
    get_instruction_content,
)


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
                                    "_managed_by": "memanto",
                                    "type": "command",
                                    "command": "memanto memory sync --project-dir .",
                                },
                                {
                                    "_managed_by": "memanto",
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
                                    "_managed_by": "memanto",
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
        {
            "matcher": "startup",
            "hooks": [{"type": "command", "command": "echo keep"}],
        },
        {"matcher": "other", "hooks": [{"command": "echo other"}]},
    ]
    assert permissions == {
        "permissions": {"allow": ["Bash(git status)"]},
        "env": {"KEEP": "1"},
    }


def test_pi_install_deploys_instructions_skill_and_extension(tmp_path, monkeypatch):
    stub_config_manager(monkeypatch)

    result = engine.install_agent("pi", str(tmp_path))

    assert result["errors"] == []
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".pi" / "skills" / "memanto" / "SKILL.md").exists()
    extension_path = tmp_path / ".pi" / "extensions" / "memanto-sync.ts"
    assert extension_path.exists()
    assert any("Deployed extension" in step for step in result["steps"])

    extension = extension_path.read_text(encoding="utf-8")
    assert 'pi.on("session_start"' in extension
    assert 'event.reason !== "startup"' in extension
    assert '"memory", "sync", "--project-dir", ctx.cwd' in extension


def test_pi_install_is_idempotent(tmp_path, monkeypatch):
    stub_config_manager(monkeypatch)

    engine.install_agent("pi", str(tmp_path))
    result = engine.install_agent("pi", str(tmp_path))

    assert result["errors"] == []
    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count(MEMANTO_SENTINEL) == 1
    assert agents_md.count(MEMANTO_SENTINEL_END) == 1
    assert list((tmp_path / ".pi" / "extensions").iterdir()) == [
        tmp_path / ".pi" / "extensions" / "memanto-sync.ts"
    ]


def test_pi_remove_deletes_extension(tmp_path, monkeypatch):
    stub_config_manager(monkeypatch)
    engine.install_agent("pi", str(tmp_path))

    result = engine.remove_agent("pi", str(tmp_path))

    assert result["errors"] == []
    assert any("Removed extension" in step for step in result["steps"])
    assert not (tmp_path / ".pi" / "extensions").exists()
    assert not (tmp_path / ".pi" / "skills" / "memanto").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_pi_global_paths_match_pi_agent_layout(tmp_path, monkeypatch):
    """Pi discovers global skills and extensions under ~/.pi/agent/."""
    stub_config_manager(monkeypatch)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = engine.install_agent("pi", str(tmp_path / "project"), is_global=True)

    assert result["errors"] == []
    assert (tmp_path / ".pi" / "agent" / "AGENTS.md").exists()
    assert (tmp_path / ".pi" / "agent" / "skills" / "memanto" / "SKILL.md").exists()
    assert (tmp_path / ".pi" / "agent" / "extensions" / "memanto-sync.ts").exists()

    remove_result = engine.remove_agent("pi", str(tmp_path / "project"), is_global=True)

    assert remove_result["errors"] == []
    assert not (tmp_path / ".pi" / "agent" / "extensions").exists()


def test_agents_without_extension_deploy_none(tmp_path, monkeypatch):
    """The extension artifact is opt-in; agents without one are unaffected."""
    stub_config_manager(monkeypatch)

    result = engine.install_agent("codex", str(tmp_path))

    assert result["errors"] == []
    assert AGENT_REGISTRY["codex"].extension_file is None
    assert not any(step.startswith("Deployed extension") for step in result["steps"])

    remove_result = engine.remove_agent("codex", str(tmp_path))

    assert remove_result["errors"] == []
    assert not any(
        step.startswith("Removed extension") for step in remove_result["steps"]
    )


def test_each_agent_gets_its_own_slug_in_skill_and_instructions():
    """A skill installed for Cursor must tell Cursor to identify as `cursor`.

    The shared templates previously hardcoded `claude_code`, so every agent
    reported the wrong writer and the connected-tools view could never be
    right.
    """
    from memanto.cli.connect.templates import (
        get_instruction_content,
        get_skill_content,
    )

    for name in AGENT_REGISTRY:
        skill = get_skill_content(name)
        instruction = get_instruction_content(name)

        # The skill is the command reference: it carries both identity flags.
        assert f"--tool {name}" in skill, f"{name}/skill missing --tool"
        assert f"--source {name}" in skill, f"{name}/skill missing --source"
        # The instruction file defers syntax to the skill, but still has to
        # tell the agent to identify itself on reads.
        assert f"--tool {name}" in instruction, f"{name}/instruction missing --tool"

        for label, text in (("skill", skill), ("instruction", instruction)):
            for stale in ("<agent_name>", "your_agent_name", "claude_code"):
                assert stale not in text, f"{name}/{label} still contains {stale}"


def test_installed_skill_carries_the_agents_own_slug(tmp_path, monkeypatch):
    stub_config_manager(monkeypatch)

    engine.install_agent("cursor", str(tmp_path))

    skill = (tmp_path / ".cursor" / "skills" / "memanto" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "--tool cursor" in skill
    assert "--tool claude-code" not in skill


def setup_kimi_dirs(tmp_path, monkeypatch):
    """Kimi hooks are user-level: config.toml lands in ~/.kimi-code."""
    stub_config_manager(monkeypatch)
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "project"
    project.mkdir()
    return home, project


def test_kimi_code_install_remove_round_trip(tmp_path, monkeypatch):
    home, project = setup_kimi_dirs(tmp_path, monkeypatch)

    install_result = engine.install_agent("kimi-code", str(project))

    assert install_result["errors"] == []
    assert (project / "AGENTS.md").exists()
    assert (project / ".kimi-code" / "skills" / "memanto" / "SKILL.md").exists()
    config_path = home / ".kimi-code" / "config.toml"
    config = config_path.read_text(encoding="utf-8")
    assert engine.TOML_HOOK_SENTINEL in config
    assert 'event = "SessionStart"' in config
    assert 'matcher = "startup|resume"' in config
    assert "--host kimi-code" in config
    assert 'pattern = "Bash(memanto *)"' in config
    assert "${SYS_EXECUTABLE}" not in config
    assert "${HOOKS_DIR}" not in config

    remove_result = engine.remove_agent("kimi-code", str(project))

    assert remove_result["errors"] == []
    remaining = config_path.read_text(encoding="utf-8")
    assert engine.TOML_HOOK_SENTINEL not in remaining
    assert "hooks" not in remaining
    assert config_path.exists()  # the user's config.toml is never deleted
    assert not (project / "AGENTS.md").exists()
    assert not (project / ".kimi-code" / "skills" / "memanto").exists()


def test_kimi_code_preserves_existing_config_toml(tmp_path, monkeypatch):
    home, project = setup_kimi_dirs(tmp_path, monkeypatch)
    kimi_dir = home / ".kimi-code"
    kimi_dir.mkdir()
    config_path = kimi_dir / "config.toml"
    original = (
        'theme = "dark"\n'
        "\n"
        "[[hooks]]\n"
        'event = "SessionStart"\n'
        'matcher = "startup"\n'
        'command = "echo user-hook"\n'
        "\n"
        "[[permission.rules]]\n"
        'decision = "deny"\n'
        'pattern = "Bash(rm *)"\n'
    )
    config_path.write_text(original, encoding="utf-8")

    install_result = engine.install_agent("kimi-code", str(project))

    assert install_result["errors"] == []
    merged = config_path.read_text(encoding="utf-8")
    assert merged.startswith(original.rstrip())
    assert engine.TOML_HOOK_SENTINEL in merged
    assert 'command = "echo user-hook"' in merged

    remove_result = engine.remove_agent("kimi-code", str(project))

    assert remove_result["errors"] == []
    assert config_path.read_text(encoding="utf-8") == original


def test_kimi_code_install_is_idempotent(tmp_path, monkeypatch):
    home, project = setup_kimi_dirs(tmp_path, monkeypatch)

    engine.install_agent("kimi-code", str(project))
    result = engine.install_agent("kimi-code", str(project))

    assert result["errors"] == []
    config = (home / ".kimi-code" / "config.toml").read_text(encoding="utf-8")
    assert config.count(engine.TOML_HOOK_SENTINEL) == 1
    assert config.count(engine.TOML_HOOK_SENTINEL_END) == 1
    agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md.count(MEMANTO_SENTINEL) == 1
    assert agents_md.count(MEMANTO_SENTINEL_END) == 1


def test_kimi_code_merged_config_parses_as_toml(tmp_path, monkeypatch):
    tomllib = pytest.importorskip("tomllib")
    home, project = setup_kimi_dirs(tmp_path, monkeypatch)
    kimi_dir = home / ".kimi-code"
    kimi_dir.mkdir()
    config_path = kimi_dir / "config.toml"
    config_path.write_text(
        '[[hooks]]\nevent = "SessionStart"\ncommand = "echo user-hook"\n',
        encoding="utf-8",
    )

    install_result = engine.install_agent("kimi-code", str(project))

    assert install_result["errors"] == []
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    events = [hook.get("event") for hook in data["hooks"]]
    assert events.count("SessionStart") == 2  # user hook + memanto hook
    assert "PreCompact" in events
    assert "PostToolUse" in events
    rules = data["permission"]["rules"]
    assert any(rule.get("pattern") == "Bash(memanto *)" for rule in rules)


def test_kimi_code_global_install_uses_kimi_code_home(tmp_path, monkeypatch):
    stub_config_manager(monkeypatch)
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = engine.install_agent(
        "kimi-code", str(tmp_path / "project"), is_global=True
    )

    assert result["errors"] == []
    assert (tmp_path / ".kimi-code" / "AGENTS.md").exists()
    assert (tmp_path / ".kimi-code" / "skills" / "memanto" / "SKILL.md").exists()
    config_path = tmp_path / ".kimi-code" / "config.toml"
    assert engine.TOML_HOOK_SENTINEL in config_path.read_text(encoding="utf-8")

    remove_result = engine.remove_agent(
        "kimi-code", str(tmp_path / "project"), is_global=True
    )

    assert remove_result["errors"] == []
    remaining = config_path.read_text(encoding="utf-8")
    assert engine.TOML_HOOK_SENTINEL not in remaining
    assert not (tmp_path / ".kimi-code" / "AGENTS.md").exists()
    assert not (tmp_path / ".kimi-code" / "skills" / "memanto").exists()


def test_kimi_code_global_install_honors_kimi_code_home_env(tmp_path, monkeypatch):
    """KIMI_CODE_HOME relocates the whole global root (default ~/.kimi-code)."""
    stub_config_manager(monkeypatch)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    kimi_home = tmp_path / "custom-kimi-root"
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home))

    result = engine.install_agent(
        "kimi-code", str(tmp_path / "project"), is_global=True
    )

    assert result["errors"] == []
    assert (kimi_home / "AGENTS.md").exists()
    assert (kimi_home / "skills" / "memanto" / "SKILL.md").exists()
    config_path = kimi_home / "config.toml"
    assert engine.TOML_HOOK_SENTINEL in config_path.read_text(encoding="utf-8")
    assert not (fake_home / ".kimi-code").exists()

    remove_result = engine.remove_agent(
        "kimi-code", str(tmp_path / "project"), is_global=True
    )

    assert remove_result["errors"] == []
    remaining = config_path.read_text(encoding="utf-8")
    assert engine.TOML_HOOK_SENTINEL not in remaining
    assert not (kimi_home / "AGENTS.md").exists()
    assert not (kimi_home / "skills" / "memanto").exists()

import importlib.util
import json
from pathlib import Path

import pytest

from memanto.cli.connect import engine, mcp_setup
from memanto.cli.connect.agent_registry import AGENT_REGISTRY
from memanto.cli.connect.templates import TEMPLATE_VERSION, get_instruction_content

AGENT = "test-agent"
MCP_PATH = str(Path("/bin/memanto-mcp").resolve())


class StubConfigManager:
    active = (AGENT, "token")

    def add_connection(self, *args, **kwargs):
        return None

    def remove_connection(self, *args, **kwargs):
        return None

    def get_active_session(self):
        return self.active


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated project + home dir, an active agent, and memanto-mcp on PATH."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    StubConfigManager.active = (AGENT, "token")
    monkeypatch.setattr(engine, "ConfigManager", StubConfigManager)
    monkeypatch.setattr(mcp_setup.shutil, "which", lambda name: "/bin/memanto-mcp")
    return home, project


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def all_text(root: Path) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in root.rglob("*")
        if p.is_file()
    )


# Instruction text


@pytest.mark.parametrize("agent_name", sorted(AGENT_REGISTRY))
def test_instruction_text_is_shared_and_safe(agent_name):
    content = get_instruction_content(agent_name)

    assert f"memanto-template-version: {TEMPLATE_VERSION}" in content
    assert "use the `memanto` MCP tools" in content
    assert "or CLI commands" in content
    # No ready-made CLI commands: agents that can use the tools should not be
    # pulled toward shell commands (Codex prefers them when they are shown).
    assert 'memanto remember "' not in content
    assert 'memanto recall "' not in content
    # Nothing that asks the model to write out its reasoning or forces an
    # evaluation step before every reply.
    lowered = content.lower()
    for phrase in ("thinking", "explanation", "mandatory first step", "echo "):
        assert phrase not in lowered


def test_instruction_text_differs_only_by_agent_id():
    def core(name):
        text = get_instruction_content(name)
        text = text[text.index("## MEMANTO") :]
        return text.replace(f"--tool {name}", "--tool <agent>")

    texts = {core(name) for name in AGENT_REGISTRY}
    assert len(texts) == 1


def test_template_version_bumped_for_update_notice():
    assert TEMPLATE_VERSION == "1.1.0"


# Claude Code


def test_claude_local_registers_server_without_api_key(env):
    home, project = env

    result = engine.install_agent("claude-code", str(project))

    assert result["errors"] == []
    entry = read_json(project / ".mcp.json")["mcpServers"]["memanto"]
    assert entry["command"] == MCP_PATH
    assert entry["env"]["MEMANTO_DEFAULT_AGENT_ID"] == AGENT
    settings = read_json(project / ".claude" / "settings.local.json")
    assert "memanto" in settings["enabledMcpjsonServers"]
    assert "mcp__memanto" in settings["permissions"]["allow"]
    assert "MOORCHEH_API_KEY" not in all_text(project)
    assert "MOORCHEH_API_KEY" not in all_text(home)


def test_claude_local_remove_cleans_up(env):
    _home, project = env
    engine.install_agent("claude-code", str(project))

    result = engine.remove_agent("claude-code", str(project))

    assert result["errors"] == []
    assert not (project / ".mcp.json").exists()
    assert not (project / ".claude" / "settings.local.json").exists()


def test_claude_keeps_user_configured_server(env):
    _home, project = env
    own = {"mcpServers": {"memanto": {"command": "my-memanto", "env": {"X": "1"}}}}
    (project / ".mcp.json").write_text(json.dumps(own), encoding="utf-8")

    result = engine.install_agent("claude-code", str(project))
    engine.remove_agent("claude-code", str(project))

    assert any("Kept your existing" in step for step in result["steps"])
    assert read_json(project / ".mcp.json") == own


def test_claude_global_uses_user_config(env):
    home, project = env
    (home / ".claude.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    engine.install_agent("claude-code", str(project), is_global=True)
    data = read_json(home / ".claude.json")
    assert data["theme"] == "dark"
    assert data["mcpServers"]["memanto"]["env"]["MEMANTO_DEFAULT_AGENT_ID"] == AGENT

    engine.remove_agent("claude-code", str(project), is_global=True)
    assert read_json(home / ".claude.json") == {"theme": "dark"}


# Codex


def test_codex_adds_managed_block_with_auto_approval(env):
    home, project = env
    config = home / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        'model = "x"\n\n[projects.foo]\ntrust_level = "trusted"\n', encoding="utf-8"
    )

    engine.install_agent("codex", str(project))
    engine.install_agent("codex", str(project))  # idempotent

    text = config.read_text(encoding="utf-8")
    assert text.count(mcp_setup.CODEX_BLOCK_START) == 1
    assert "[mcp_servers.memanto]" in text
    assert 'default_tools_approval_mode = "approve"' in text
    assert f'MEMANTO_DEFAULT_AGENT_ID = "{AGENT}"' in text
    assert 'env_vars = ["USERPROFILE", "HOME"' in text
    assert "MOORCHEH_API_KEY" not in text
    assert text.startswith('model = "x"\n\n[projects.foo]')

    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        tomllib = pytest.importorskip("tomli")
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["memanto"]["command"] == MCP_PATH
    assert "USERPROFILE" in parsed["mcp_servers"]["memanto"]["env_vars"]


def test_codex_local_remove_keeps_shared_entry_global_remove_drops_it(env):
    home, project = env
    config = home / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('model = "x"\n', encoding="utf-8")
    engine.install_agent("codex", str(project))

    engine.remove_agent("codex", str(project))
    assert mcp_setup.CODEX_BLOCK_START in config.read_text(encoding="utf-8")

    engine.remove_agent("codex", str(project), is_global=True)
    assert config.read_text(encoding="utf-8") == 'model = "x"\n'


def test_codex_keeps_user_configured_server(env):
    home, project = env
    config = home / ".codex" / "config.toml"
    config.parent.mkdir()
    own = '[mcp_servers.memanto]\ncommand = "memanto-mcp"\nenv = { MOORCHEH_API_KEY = "k" }\n'
    config.write_text(own, encoding="utf-8")

    result = engine.install_agent("codex", str(project))

    assert any("Kept your existing" in step for step in result["steps"])
    assert config.read_text(encoding="utf-8") == own


# Cursor


def test_cursor_local_registers_and_removes(env):
    _home, project = env

    engine.install_agent("cursor", str(project))
    entry = read_json(project / ".cursor" / "mcp.json")["mcpServers"]["memanto"]
    assert entry["env"]["MEMANTO_DEFAULT_AGENT_ID"] == AGENT
    assert "MOORCHEH_API_KEY" not in json.dumps(entry)

    engine.remove_agent("cursor", str(project))
    assert not (project / ".cursor" / "mcp.json").exists()


# Skips


def test_no_active_agent_skips_mcp(env):
    _home, project = env
    StubConfigManager.active = (None, None)

    result = engine.install_agent("cursor", str(project))

    assert any("no active memanto agent" in step for step in result["steps"])
    assert not (project / ".cursor" / "mcp.json").exists()


def test_missing_memanto_mcp_skips(env, monkeypatch):
    _home, project = env
    monkeypatch.setattr(mcp_setup.shutil, "which", lambda name: None)
    monkeypatch.setattr(mcp_setup.importlib.util, "find_spec", lambda name: None)

    result = engine.install_agent("cursor", str(project))

    assert any("memanto-mcp is not installed" in step for step in result["steps"])
    assert not (project / ".cursor" / "mcp.json").exists()


def test_agents_without_mcp_client_write_no_mcp_config(env):
    home, project = env

    engine.install_agent("gemini-cli", str(project))

    assert not (project / ".mcp.json").exists()
    assert not (home / ".codex").exists()


# Notify hook

HOOK = (
    Path(__file__).resolve().parents[1]
    / "memanto"
    / "cli"
    / "connect"
    / "assets"
    / "hooks"
    / "notify.py"
)


@pytest.fixture
def notify():
    spec = importlib.util.spec_from_file_location("notify_hook", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notify_describes_mcp_tools(notify):
    assert (
        notify.describe_mcp("remember", {"type": "instruction"}, "")
        == "stored an instruction"
    )
    assert (
        notify.describe_mcp(
            "batch_remember", {"memories": [1, 2, 3]}, '{"successful": 2}'
        )
        == "stored 2 memories"
    )
    assert (
        notify.describe_mcp("batch_remember", {"memories": [1]}, '{"successful": 0}')
        is None
    )
    assert notify.describe_mcp("recall", {}, '{"count": 3}') == "recalled 3 memories"
    assert notify.describe_mcp("recall", {}, "not json") == "searched memory"
    assert notify.describe_mcp("answer", {}, "x") == "answered from memory"


def test_hooks_register_notify_for_mcp_tools():
    hooks = json.loads((HOOK.parent / "hooks.json").read_text(encoding="utf-8"))[
        "hooks"
    ]
    matchers = [group.get("matcher") for group in hooks["PostToolUse"]]
    assert "mcp__memanto__.*" in matchers


def test_mcp_agents_skip_cli_skill_and_remove_old_one(env):
    _home, project = env
    old_skill = project / ".agents" / "skills" / "memanto" / "SKILL.md"
    old_skill.parent.mkdir(parents=True)
    old_skill.write_text("old cli skill", encoding="utf-8")

    result = engine.install_agent("codex", str(project))

    assert result["errors"] == []
    assert not old_skill.exists()
    assert any("MCP tools are used instead" in step for step in result["steps"])


def test_skill_still_installed_when_mcp_is_skipped(env):
    _home, project = env
    StubConfigManager.active = (None, None)

    engine.install_agent("cursor", str(project))

    assert (project / ".cursor" / "skills" / "memanto" / "SKILL.md").exists()


def test_server_command_is_absolute_path(env):
    command, args = mcp_setup.server_command()
    assert Path(command).is_absolute()
    assert args == []


def test_codex_reports_shared_agent_change(env):
    _home, project = env
    engine.install_agent("codex", str(project))
    StubConfigManager.active = ("other-agent", "token")

    result = engine.install_agent("codex", str(project))

    assert any(
        "agent changed from 'test-agent' to 'other-agent'" in s for s in result["steps"]
    )


def test_claude_does_not_approve_or_unapprove_user_server(env):
    _home, project = env
    own = {"mcpServers": {"memanto": {"command": "my-memanto"}}}
    (project / ".mcp.json").write_text(json.dumps(own), encoding="utf-8")
    settings = project / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps({"enabledMcpjsonServers": ["memanto"]}), encoding="utf-8"
    )

    engine.install_agent("claude-code", str(project))
    assert read_json(settings)["enabledMcpjsonServers"] == ["memanto"]

    engine.remove_agent("claude-code", str(project))
    assert read_json(settings)["enabledMcpjsonServers"] == ["memanto"]

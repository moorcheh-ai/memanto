"""
MEMANTO CLI - Agent Registry

Defines all supported AI coding agents with their instruction file paths,
skill directories, and integration capabilities.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentHookConfig:
    """Hook configuration for agents that support auto-sync."""

    settings_file: str  # e.g. "settings.json"
    hook_key: str  # e.g. "hooks.SessionStart"
    hook_payload: dict = field(default_factory=dict)


@dataclass
class AgentDef:
    """Definition of a supported AI coding agent."""

    name: str  # CLI identifier, e.g. "claude-code"
    display_name: str  # Human name, e.g. "Claude Code"

    # Instruction file (the main file where agent reads instructions)
    instruction_file: str | None = None  # e.g. "CLAUDE.md"
    instruction_format: str = "markdown"  # "markdown" | "mdc" | "append"

    # Skill directory paths (relative)
    skill_local_dir: str | None = None  # e.g. ".claude/skills/"
    skill_global_dir: str | None = None  # e.g. "~/.claude/skills/"

    # Hook support
    supports_hooks: bool = False
    hook_config: AgentHookConfig | None = None

    # Config directory (for settings, permissions, etc.)
    config_local_dir: str | None = None  # e.g. ".claude/"
    config_global_dir: str | None = None  # e.g. "~/.claude/"

    # Sentinel for idempotent instruction injection
    sentinel: str = "<!-- MEMANTO-MANAGED-SECTION -->"
    sentinel_end: str = "<!-- /MEMANTO-MANAGED-SECTION -->"

    # Whether instruction file is a directory (like .clinerules/)
    instruction_is_dir: bool = False

    # Permission configuration (agent-specific)
    permissions_file: str | None = None  # e.g. "settings.local.json"
    permissions_payload: dict | None = None

    def resolve_skill_local(self, project_dir: Path) -> Path:
        """Resolve local skill directory path."""
        if self.skill_local_dir:
            return project_dir / self.skill_local_dir / "memanto"
        return project_dir / ".agents" / "skills" / "memanto"

    def resolve_skill_global(self) -> Path:
        """Resolve global skill directory path."""
        if self.skill_global_dir:
            return Path.home() / self.skill_global_dir.lstrip("~/") / "memanto"
        return Path.home() / ".agents" / "skills" / "memanto"

    def resolve_instruction_file(
        self, project_dir: Path, is_global: bool
    ) -> Path | None:
        """Resolve instruction file path."""
        if not self.instruction_file:
            return None
        if is_global:
            if self.config_global_dir:
                base = Path.home() / self.config_global_dir.lstrip("~/")
            else:
                base = Path.home()
            return base / self.instruction_file
        return project_dir / self.instruction_file


# Agent Definitions

CLAUDE_CODE = AgentDef(
    name="claude-code",
    display_name="Claude Code",
    instruction_file="CLAUDE.md",
    instruction_format="markdown",
    skill_local_dir=".claude/skills",
    skill_global_dir="~/.claude/skills",
    config_local_dir=".claude",
    config_global_dir="~/.claude",
    supports_hooks=True,
    hook_config=AgentHookConfig(
        settings_file="settings.json",
        hook_key="hooks.SessionStart",
        hook_payload={
            "matcher": "startup",
            "hooks": [
                {
                    "type": "command",
                    "command": "memanto memory sync --project-dir .",
                    "timeout": 30,
                }
            ],
        },
    ),
    permissions_file="settings.local.json",
    permissions_payload={"permissions": {"allow": ["Bash(memanto:*)"]}},
)

CODEX = AgentDef(
    name="codex",
    display_name="Codex CLI",
    instruction_file="AGENTS.md",
    instruction_format="markdown",
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.codex/skills",
    config_local_dir=".agents",
    config_global_dir="~/.codex",
)

CURSOR = AgentDef(
    name="cursor",
    display_name="Cursor",
    instruction_file=".cursor/rules/memanto.mdc",
    instruction_format="mdc",
    skill_local_dir=".cursor/skills",
    skill_global_dir="~/.cursor/skills",
    config_local_dir=".cursor",
    config_global_dir="~/.cursor",
)

WINDSURF = AgentDef(
    name="windsurf",
    display_name="Windsurf",
    instruction_file=".windsurfrules",
    instruction_format="append",
    skill_local_dir=".windsurf/skills",
    skill_global_dir="~/.codeium/windsurf/skills",
    config_local_dir=".windsurf",
    config_global_dir="~/.codeium/windsurf",
)

ANTIGRAVITY = AgentDef(
    name="antigravity",
    display_name="Antigravity (Google)",
    instruction_file=None,  # Antigravity uses skills only
    skill_local_dir=".agent/skills",
    skill_global_dir="~/.gemini/antigravity/skills",
    config_local_dir=".agent",
    config_global_dir="~/.gemini/antigravity",
)

GEMINI_CLI = AgentDef(
    name="gemini-cli",
    display_name="Gemini CLI",
    instruction_file="GEMINI.md",
    instruction_format="markdown",
    skill_local_dir=".gemini/skills",
    skill_global_dir="~/.gemini/skills",
    config_local_dir=".gemini",
    config_global_dir="~/.gemini",
)

CLINE = AgentDef(
    name="cline",
    display_name="Cline",
    instruction_file=".clinerules/memanto.md",
    instruction_format="markdown",
    instruction_is_dir=True,
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.agents/skills",
    config_local_dir=".clinerules",
)

CONTINUE = AgentDef(
    name="continue",
    display_name="Continue",
    instruction_file=".continue/rules/memanto.md",
    instruction_format="markdown",
    instruction_is_dir=True,
    skill_local_dir=".continue/skills",
    skill_global_dir="~/.continue/skills",
    config_local_dir=".continue",
    config_global_dir="~/.continue",
)

OPENCODE = AgentDef(
    name="opencode",
    display_name="OpenCode",
    instruction_file="AGENTS.md",
    instruction_format="markdown",
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.config/opencode/skills",
    config_global_dir="~/.config/opencode",
)

GOOSE = AgentDef(
    name="goose",
    display_name="Goose",
    instruction_file=None,  # Goose uses config.yaml + MCP, not an instruction file
    skill_local_dir=".goose/skills",
    skill_global_dir="~/.config/goose/skills",
    config_local_dir=".goose",
    config_global_dir="~/.config/goose",
)

ROO = AgentDef(
    name="roo",
    display_name="Roo Code",
    instruction_file=".roo/rules/memanto.md",
    instruction_format="markdown",
    instruction_is_dir=True,
    skill_local_dir=".roo/skills",
    skill_global_dir="~/.roo/skills",
    config_local_dir=".roo",
    config_global_dir="~/.roo",
)

GITHUB_COPILOT = AgentDef(
    name="github-copilot",
    display_name="GitHub Copilot",
    instruction_file=".github/copilot-instructions.md",
    instruction_format="markdown",
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.copilot/skills",
    config_local_dir=".github",
)

AUGMENT = AgentDef(
    name="augment",
    display_name="Augment Code",
    instruction_file=".augment/rules/memanto.md",
    instruction_format="markdown",
    instruction_is_dir=True,
    skill_local_dir=".augment/skills",
    skill_global_dir="~/.augment/skills",
    config_local_dir=".augment",
    config_global_dir="~/.augment",
)


# Registry

AGENT_REGISTRY: dict[str, AgentDef] = {
    a.name: a
    for a in [
        CLAUDE_CODE,
        CODEX,
        CURSOR,
        WINDSURF,
        ANTIGRAVITY,
        GEMINI_CLI,
        CLINE,
        CONTINUE,
        OPENCODE,
        GOOSE,
        ROO,
        GITHUB_COPILOT,
        AUGMENT,
    ]
}


def get_agent(name: str) -> AgentDef | None:
    """Get agent definition by name."""
    return AGENT_REGISTRY.get(name)


def list_agents() -> list[AgentDef]:
    """List all supported agents in display order."""
    return list(AGENT_REGISTRY.values())


def detect_agents_in_project(project_dir: Path) -> list[AgentDef]:
    """Auto-detect which agents are present in a project directory.

    Checks for the existence of agent-specific config directories or files.
    """
    detected = []
    for agent in AGENT_REGISTRY.values():
        # Check for config directory
        if agent.config_local_dir:
            config_path = project_dir / agent.config_local_dir
            if config_path.exists():
                detected.append(agent)
                continue
        # Check for instruction file
        if agent.instruction_file:
            instr_path = project_dir / agent.instruction_file
            # For directory-based instruction files, check parent dir
            if agent.instruction_is_dir:
                parent = instr_path.parent
                if parent.exists():
                    detected.append(agent)
                    continue
            elif instr_path.exists():
                detected.append(agent)
                continue
    return detected


def detect_memanto_installed(project_dir: Path) -> list[AgentDef]:
    """Detect which agents have MEMANTO already installed (local)."""
    installed = []
    for agent in AGENT_REGISTRY.values():
        if _has_memanto_skill(agent, project_dir, is_global=False) and (
            not agent.instruction_file
            or _has_memanto_instruction(agent, project_dir, is_global=False)
        ):
            installed.append(agent)
    return installed


def detect_memanto_installed_global() -> list[AgentDef]:
    """Detect which agents have MEMANTO installed globally."""
    installed = []
    for agent in AGENT_REGISTRY.values():
        if _has_memanto_skill(agent, Path.home(), is_global=True) and (
            not agent.instruction_file
            or _has_memanto_instruction(agent, Path.home(), is_global=True)
        ):
            installed.append(agent)
    return installed


def _has_memanto_skill(agent: AgentDef, project_dir: Path, is_global: bool) -> bool:
    skill_dir = (
        agent.resolve_skill_global()
        if is_global
        else agent.resolve_skill_local(project_dir)
    )
    return (skill_dir / "SKILL.md").is_file()


def _has_memanto_instruction(
    agent: AgentDef, project_dir: Path, is_global: bool
) -> bool:
    instr_path = agent.resolve_instruction_file(project_dir, is_global)
    if instr_path is None or not instr_path.is_file():
        return False
    try:
        content = instr_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return agent.sentinel in content and agent.sentinel_end in content

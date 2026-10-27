"""
MEMANTO CLI - Agent Registry

Defines all supported AI coding agents with their instruction file paths,
skill directories, and integration capabilities.
"""

import os
import platform
from dataclasses import dataclass
from pathlib import Path


def _get_vscode_prompts_dir() -> str:
    system = platform.system()
    if system == "Windows":
        home = Path.home()
        appdata = os.environ.get("APPDATA")
        if appdata:
            appdata_path = Path(appdata)
            try:
                appdata_path.relative_to(Path(os.path.expanduser("~")))
                # If Path.home() was overridden (e.g. in tests), stay under Path.home()
                if home != Path(os.path.expanduser("~")):
                    base = str(home / "AppData" / "Roaming")
                else:
                    base = appdata
            except ValueError:
                base = appdata
        else:
            base = str(home / "AppData" / "Roaming")
        return os.path.join(base, "Code", "User", "prompts", "memanto.instructions.md")
    elif system == "Darwin":
        return "~/Library/Application Support/Code/User/prompts/memanto.instructions.md"
    else:
        return "~/.config/Code/User/prompts/memanto.instructions.md"


def _get_goose_config_dir() -> str:
    system = platform.system()
    if system == "Windows":
        home = Path.home()
        appdata = os.environ.get("APPDATA")
        if appdata:
            appdata_path = Path(appdata)
            try:
                appdata_path.relative_to(Path(os.path.expanduser("~")))
                if home != Path(os.path.expanduser("~")):
                    base = str(home / "AppData" / "Roaming")
                else:
                    base = appdata
            except ValueError:
                base = appdata
        else:
            base = str(home / "AppData" / "Roaming")
        return os.path.join(base, "Block", "goose", "config")
    return "~/.config/goose"


def _get_goose_global_hints_file() -> str:
    return os.path.join(_get_goose_config_dir(), ".goosehints")


def _get_goose_global_skills_dir() -> str:
    return os.path.join(_get_goose_config_dir(), "skills")


@dataclass
class AgentHookConfig:
    """Hook configuration for agents that support auto-sync."""

    settings_file: str  # e.g. "settings.json"
    hook_key: str  # e.g. "hooks.SessionStart"
    asset_file: str | None = (
        None  # e.g. "hooks.json", "cursor-hooks.json", "codex-hooks.json"
    )


@dataclass
class AgentDef:
    """Definition of a supported AI coding agent."""

    name: str  # CLI identifier, e.g. "claude-code"
    display_name: str  # Human name, e.g. "Claude Code"

    # Instruction file (the main file where agent reads instructions)
    instruction_local_file: str | None = None  # e.g. "CLAUDE.md"
    instruction_global_file: str | None = None  # e.g. "~/.claude/CLAUDE.md"
    instruction_extra_global_files: tuple[str, ...] = ()
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
    permissions_global_file: str | None = None  # e.g. "settings.json"
    permissions_payload: dict | None = None

    # Code extension file (for agents that load native extensions, e.g. Pi .ts)
    extension_file: str | None = None  # e.g. "memanto-sync.ts"
    extension_global_dir: str | None = None  # e.g. "~/.pi/agent/extensions"
    extension_local_dir: str | None = None  # e.g. ".pi/extensions"

    # MCP client kind for registering memanto-mcp ("claude" | "codex" | "cursor").
    # Agents without one keep using the CLI through the instruction text.
    mcp_client: str | None = None

    def resolve_skill_local(self, project_dir: Path) -> Path:
        """Resolve local skill directory path."""
        if self.skill_local_dir:
            target = project_dir / self.skill_local_dir / "memanto"
            if not target.exists() and self.name == "github-copilot":
                for fallback in (
                    project_dir / ".github" / "skills" / "memanto",
                    project_dir / ".agents" / "skills" / "memanto",
                    project_dir / ".github" / "prompts" / "memanto",
                ):
                    if fallback.exists():
                        return fallback
            return target
        return project_dir / ".agents" / "skills" / "memanto"

    def resolve_skill_global(self) -> Path:
        """Resolve global skill directory path."""
        if self.name == "goose":
            return self._resolve_global_path(_get_goose_global_skills_dir()) / "memanto"
        if self.skill_global_dir:
            return self._resolve_global_path(self.skill_global_dir) / "memanto"
        return Path.home() / ".agents" / "skills" / "memanto"

    def _resolve_global_path(self, raw_path: str) -> Path:
        p = Path(raw_path)
        if p.is_absolute():
            return p
        if raw_path.startswith("~/"):
            return Path.home() / raw_path[2:]
        return Path.home() / raw_path

    def resolve_instruction_file(
        self, project_dir: Path, is_global: bool
    ) -> Path | None:
        """Resolve instruction file path."""
        if is_global:
            if not self.instruction_global_file:
                return None
            if self.name == "github-copilot":
                return self._resolve_global_path(_get_vscode_prompts_dir())
            if self.name == "goose":
                return self._resolve_global_path(_get_goose_global_hints_file())
            return self._resolve_global_path(self.instruction_global_file)
        else:
            if not self.instruction_local_file:
                return None
            target = project_dir / self.instruction_local_file
            if not target.exists() and self.name == "github-copilot":
                for fallback in (
                    project_dir / ".github" / "copilot-instructions.md",
                    project_dir
                    / ".github"
                    / "instructions"
                    / "memanto.instructions.md",
                    project_dir / ".github" / "prompts" / "memanto.instructions.md",
                ):
                    if fallback.exists():
                        return fallback
            return target

    def resolve_instruction_files(
        self, project_dir: Path, is_global: bool
    ) -> list[Path]:
        """Resolve all instruction file paths for this agent and scope."""
        primary = self.resolve_instruction_file(project_dir, is_global)
        if primary is None:
            return []
        files = [primary]
        if is_global:
            for extra in self.instruction_extra_global_files:
                resolved = self._resolve_global_path(extra)
                if resolved not in files:
                    files.append(resolved)
        return files

    def resolve_extension_file(self, project_dir: Path, is_global: bool) -> Path | None:
        """Resolve code extension file path (for agents that support one)."""
        if not self.extension_file:
            return None
        if is_global:
            if not self.extension_global_dir:
                return None
            base = Path.home() / self.extension_global_dir.lstrip("~/")
        else:
            if not self.extension_local_dir:
                return None
            base = project_dir / self.extension_local_dir
        return base / self.extension_file


# Agent Definitions

CLAUDE_CODE = AgentDef(
    name="claude-code",
    display_name="Claude Code",
    instruction_local_file="CLAUDE.md",
    instruction_global_file="~/.claude/CLAUDE.md",
    instruction_format="markdown",
    skill_local_dir=".claude/skills",
    skill_global_dir="~/.claude/skills",
    config_local_dir=".claude",
    config_global_dir="~/.claude",
    supports_hooks=True,
    hook_config=AgentHookConfig(
        settings_file="settings.json",
        hook_key="hooks.SessionStart",
        asset_file="hooks.json",
    ),
    permissions_file="settings.local.json",
    permissions_global_file="settings.json",
    permissions_payload={"permissions": {"allow": ["Bash(memanto:*)", "mcp__memanto"]}},
    mcp_client="claude",
)

CODEX = AgentDef(
    name="codex",
    display_name="Codex CLI",
    instruction_local_file="AGENTS.md",
    instruction_global_file="~/.codex/AGENTS.md",
    instruction_format="markdown",
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.codex/skills",
    config_local_dir=".agents",
    config_global_dir="~/.codex",
    supports_hooks=True,
    hook_config=AgentHookConfig(
        settings_file="hooks.json",
        hook_key="hooks.SessionStart",
        asset_file="codex-hooks.json",
    ),
    mcp_client="codex",
)

PI = AgentDef(
    name="pi",
    display_name="Pi (coding agent)",
    instruction_local_file="AGENTS.md",
    instruction_global_file="~/.pi/agent/AGENTS.md",
    instruction_format="markdown",
    skill_local_dir=".pi/skills",
    skill_global_dir="~/.pi/agent/skills",
    config_local_dir=".pi",
    config_global_dir="~/.pi/agent",
    extension_file="memanto-sync.ts",
    extension_global_dir="~/.pi/agent/extensions",
    extension_local_dir=".pi/extensions",
)

CURSOR = AgentDef(
    name="cursor",
    display_name="Cursor",
    instruction_local_file=".cursor/rules/memanto.mdc",
    instruction_global_file="~/.cursor/rules/memanto.mdc",
    instruction_format="mdc",
    skill_local_dir=".cursor/skills",
    skill_global_dir="~/.cursor/skills",
    config_local_dir=".cursor",
    config_global_dir="~/.cursor",
    supports_hooks=True,
    hook_config=AgentHookConfig(
        settings_file="hooks.json",
        hook_key="hooks.sessionStart",
        asset_file="cursor-hooks.json",
    ),
    mcp_client="cursor",
)

WINDSURF = AgentDef(
    name="windsurf",
    display_name="Windsurf",
    instruction_local_file=".windsurfrules",
    instruction_global_file="~/.codeium/windsurf/.windsurfrules",
    instruction_extra_global_files=("~/.codeium/windsurf/memories/global_rules.md",),
    instruction_format="append",
    skill_local_dir=".windsurf/skills",
    skill_global_dir="~/.codeium/windsurf/skills",
    config_local_dir=".windsurf",
    config_global_dir="~/.codeium/windsurf",
)

ANTIGRAVITY = AgentDef(
    name="antigravity",
    display_name="Antigravity (Google)",
    instruction_local_file=None,  # Antigravity uses skills only
    instruction_global_file=None,
    skill_local_dir=".agent/skills",
    skill_global_dir="~/.gemini/antigravity/skills",
    config_local_dir=".agent",
    config_global_dir="~/.gemini/antigravity",
)

GEMINI_CLI = AgentDef(
    name="gemini-cli",
    display_name="Gemini CLI",
    instruction_local_file="GEMINI.md",
    instruction_global_file="~/.gemini/GEMINI.md",
    instruction_format="markdown",
    skill_local_dir=".gemini/skills",
    skill_global_dir="~/.gemini/skills",
    config_local_dir=".gemini",
    config_global_dir="~/.gemini",
)

CLINE = AgentDef(
    name="cline",
    display_name="Cline",
    instruction_local_file=".clinerules/memanto.md",
    instruction_global_file="~/.cline/rules/memanto.md",
    instruction_format="markdown",
    instruction_is_dir=True,
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.agents/skills",
    config_local_dir=".clinerules",
    config_global_dir="~/.cline",
)

CONTINUE = AgentDef(
    name="continue",
    display_name="Continue",
    instruction_local_file=".continue/rules/memanto.md",
    instruction_global_file="~/.continue/rules/memanto.md",
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
    instruction_local_file="AGENTS.md",
    instruction_global_file="~/.config/opencode/AGENTS.md",
    instruction_format="markdown",
    skill_local_dir=".agents/skills",
    skill_global_dir="~/.config/opencode/skills",
    config_global_dir="~/.config/opencode",
)

GOOSE = AgentDef(
    name="goose",
    display_name="Goose",
    instruction_local_file=".goosehints",
    instruction_global_file=_get_goose_global_hints_file(),
    instruction_extra_global_files=("~/.config/goose/.goosehints",),
    instruction_format="append",
    skill_local_dir=".goose/skills",
    skill_global_dir=_get_goose_global_skills_dir(),
    config_local_dir=".goose",
    config_global_dir="~/.config/goose",
)

ROO = AgentDef(
    name="roo",
    display_name="Roo Code",
    instruction_local_file=".roo/rules/memanto.md",
    instruction_global_file="~/.roo/rules/memanto.md",
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
    instruction_local_file=".github/copilot-instructions.md",
    instruction_global_file=_get_vscode_prompts_dir(),
    instruction_extra_global_files=("~/.copilot/copilot-instructions.md",),
    instruction_format="markdown",
    skill_local_dir=".github/skills",
    skill_global_dir="~/.copilot/skills",
    config_local_dir=".github",
    mcp_client="github-copilot",
)

AUGMENT = AgentDef(
    name="augment",
    display_name="Augment Code",
    instruction_local_file=".augment/rules/memanto.md",
    instruction_global_file="~/.augment/rules/memanto.md",
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
        PI,
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
        if agent.instruction_local_file:
            instr_path = project_dir / agent.instruction_local_file
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
            not agent.instruction_local_file
            or _has_memanto_instruction(agent, project_dir, is_global=False)
        ):
            installed.append(agent)
    return installed


def detect_memanto_installed_global() -> list[AgentDef]:
    """Detect which agents have MEMANTO installed globally."""
    installed = []
    for agent in AGENT_REGISTRY.values():
        if _has_memanto_skill(agent, Path.home(), is_global=True) and (
            not agent.instruction_global_file
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

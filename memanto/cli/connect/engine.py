"""
MEMANTO CLI - Connect Engine

Core logic for installing/removing MEMANTO integration to AI coding agents.
Handles instruction injection, skill deployment, and hook configuration.
"""

import json
import re
from pathlib import Path
from typing import Any

from memanto.cli.config.manager import ConfigManager
from memanto.cli.connect.agent_registry import AGENT_REGISTRY, AgentDef
from memanto.cli.connect.templates import (
    MEMANTO_SENTINEL,
    MEMANTO_SENTINEL_END,
    get_instruction_content,
    get_skill_content,
)


def install_agent(
    agent_name: str,
    project_dir: str = ".",
    is_global: bool = False,
) -> dict[str, Any]:
    """Install MEMANTO integration for a single agent.

    Returns a result dict with keys:
        agent: str, steps: list[str], errors: list[str]
    """
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        return {
            "agent": agent_name,
            "steps": [],
            "errors": [f"Unknown agent: {agent_name}"],
        }

    project_path = Path(project_dir).resolve()
    steps: list[str] = []
    errors: list[str] = []

    # Instruction file
    try:
        instr_result = _install_instructions(agent, project_path, is_global)
        if instr_result:
            steps.append(instr_result)
    except Exception as e:
        errors.append(f"Instruction file: {e}")

    # Skill deployment
    try:
        skill_result = _install_skill(agent, project_path, is_global)
        if skill_result:
            steps.append(skill_result)
    except Exception as e:
        errors.append(f"Skill deployment: {e}")

    # Hook configuration (only Claude Code currently)
    if agent.supports_hooks and agent.hook_config:
        try:
            hook_result = _install_hooks(agent, project_path, is_global)
            if hook_result:
                steps.append(hook_result)
        except Exception as e:
            errors.append(f"Hook configuration: {e}")

    # Permissions (agent-specific)
    if agent.permissions_file and agent.permissions_payload:
        try:
            perm_result = _install_permissions(agent, project_path, is_global)
            if perm_result:
                steps.append(perm_result)
        except Exception as e:
            errors.append(f"Permissions: {e}")

    if steps:
        try:
            ConfigManager().add_connection(
                agent_name, str(project_path) if not is_global else None, is_global
            )
        except Exception as e:
            errors.append(f"Registry sync: {e}")

    return {"agent": agent_name, "steps": steps, "errors": errors}


def remove_agent(
    agent_name: str,
    project_dir: str = ".",
    is_global: bool = False,
) -> dict[str, Any]:
    """Remove MEMANTO integration for a single agent."""
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        return {
            "agent": agent_name,
            "steps": [],
            "errors": [f"Unknown agent: {agent_name}"],
        }

    project_path = Path(project_dir).resolve()
    steps: list[str] = []
    errors: list[str] = []

    # Remove instruction content
    try:
        result = _remove_instructions(agent, project_path, is_global)
        if result:
            steps.append(result)
    except Exception as e:
        errors.append(f"Instruction removal: {e}")

    # Remove skill directory
    try:
        result = _remove_skill(agent, project_path, is_global)
        if result:
            steps.append(result)
    except Exception as e:
        errors.append(f"Skill removal: {e}")

    try:
        ConfigManager().remove_connection(
            agent_name, str(project_path) if not is_global else None, is_global
        )
    except Exception as e:
        errors.append(f"Registry sync: {e}")

    return {"agent": agent_name, "steps": steps, "errors": errors}


# Internal: Instruction file management


def _install_instructions(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Install MEMANTO instructions into the agent's instruction file."""
    if not agent.instruction_file:
        return None  # Agent doesn't use instruction files (skills-only)

    instr_path = agent.resolve_instruction_file(project_path, is_global)
    if not instr_path:
        return None

    content = get_instruction_content(agent.name)

    # For agents with directory-based instruction files (cline, roo, continue, augment)
    if agent.instruction_is_dir:
        return _write_dedicated_file(instr_path, content)

    # For MDC format (Cursor)
    if agent.instruction_format == "mdc":
        return _write_dedicated_file(instr_path, content)

    # For agents that use append-style (Windsurf .windsurfrules)
    if agent.instruction_format == "append":
        return _inject_into_file(instr_path, content, create_if_missing=True)

    # For standard markdown files (CLAUDE.md, AGENTS.md, GEMINI.md, copilot-instructions.md)
    return _inject_into_file(instr_path, content, create_if_missing=True)


def _write_dedicated_file(file_path: Path, content: str) -> str:
    """Write content to a dedicated file (creates parent dirs)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        if MEMANTO_SENTINEL in existing:
            # Replace existing section
            pattern = (
                re.escape(MEMANTO_SENTINEL) + r".*?" + re.escape(MEMANTO_SENTINEL_END)
            )
            updated = re.sub(pattern, content.strip(), existing, flags=re.DOTALL)
            file_path.write_text(updated, encoding="utf-8")
            return f"Updated {file_path.name}"

    file_path.write_text(content.strip() + "\n", encoding="utf-8")
    return f"Created {file_path.name}"


def _inject_into_file(
    file_path: Path, section: str, create_if_missing: bool = True
) -> str | None:
    """Inject MEMANTO section into an existing file, or create it."""
    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        if MEMANTO_SENTINEL in existing:
            # Replace existing section
            pattern = (
                re.escape(MEMANTO_SENTINEL) + r".*?" + re.escape(MEMANTO_SENTINEL_END)
            )
            updated = re.sub(pattern, section.strip(), existing, flags=re.DOTALL)
            file_path.write_text(updated, encoding="utf-8")
            return f"Updated MEMANTO section in {file_path.name}"
        else:
            # Insert before first ## heading, or append
            match = re.search(r"^## ", existing, flags=re.MULTILINE)
            if match:
                insert_pos = match.start()
                updated = (
                    existing[:insert_pos].rstrip()
                    + "\n\n"
                    + section.strip()
                    + "\n\n"
                    + existing[insert_pos:]
                )
            else:
                updated = existing.rstrip() + "\n\n" + section.strip() + "\n"
            file_path.write_text(updated, encoding="utf-8")
            return f"Added MEMANTO section to {file_path.name}"
    elif create_if_missing:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(section.strip() + "\n", encoding="utf-8")
        return f"Created {file_path.name}"

    return None


def _remove_instructions(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Remove MEMANTO instructions from the agent's instruction file."""
    if not agent.instruction_file:
        return None

    instr_path = agent.resolve_instruction_file(project_path, is_global)
    if not instr_path or not instr_path.exists():
        return None

    # For dedicated files (cline, roo, continue, augment, cursor)
    if agent.instruction_is_dir or agent.instruction_format == "mdc":
        instr_path.unlink()
        # Clean up empty parent dirs
        parent = instr_path.parent
        try:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass
        return f"Removed {instr_path.name}"

    # For shared files (CLAUDE.md, AGENTS.md, etc.), remove the section
    existing = instr_path.read_text(encoding="utf-8")
    if MEMANTO_SENTINEL in existing:
        pattern = re.escape(MEMANTO_SENTINEL) + r".*?" + re.escape(MEMANTO_SENTINEL_END)
        updated = re.sub(pattern, "", existing, flags=re.DOTALL)
        # Clean up extra whitespace
        updated = re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"
        if updated.strip():
            instr_path.write_text(updated, encoding="utf-8")
            return f"Removed MEMANTO section from {instr_path.name}"
        else:
            instr_path.unlink()
            return f"Removed {instr_path.name} (was empty)"

    return None


# Internal: Skill deployment


def _install_skill(agent: AgentDef, project_path: Path, is_global: bool) -> str:
    """Deploy SKILL.md to the agent's skill directory."""
    if is_global:
        skill_dir = agent.resolve_skill_global()
    else:
        skill_dir = agent.resolve_skill_local(project_path)

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(get_skill_content(), encoding="utf-8")

    rel = _display_path(skill_path, is_global)
    return f"Deployed skill to {rel}"


def _remove_skill(agent: AgentDef, project_path: Path, is_global: bool) -> str | None:
    """Remove SKILL.md from the agent's skill directory."""
    if is_global:
        skill_dir = agent.resolve_skill_global()
    else:
        skill_dir = agent.resolve_skill_local(project_path)

    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        skill_path.unlink()
        # Clean up empty dirs
        try:
            if skill_dir.exists() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()
        except Exception:
            pass
        return f"Removed skill from {_display_path(skill_dir, is_global)}"
    return None


# Internal: Hook configuration (Claude Code)


def _install_hooks(agent: AgentDef, project_path: Path, is_global: bool) -> str | None:
    """Configure auto-sync hooks for agents that support them."""
    if not agent.hook_config:
        return None

    if is_global:
        if agent.config_global_dir:
            config_dir = Path.home() / agent.config_global_dir.lstrip("~/")
        else:
            return None
    else:
        if agent.config_local_dir:
            config_dir = project_path / agent.config_local_dir
        else:
            return None

    config_dir.mkdir(parents=True, exist_ok=True)
    settings_path = config_dir / agent.hook_config.settings_file

    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {}

    # Navigate to hook location
    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])

    # Check if memanto hook already exists
    memanto_exists = any(
        isinstance(group, dict)
        and any(
            isinstance(h, dict) and "memanto" in h.get("command", "")
            for h in group.get("hooks", [])
        )
        for group in session_start
    )

    if not memanto_exists:
        session_start.append(agent.hook_config.hook_payload)
        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        return "Added SessionStart hook"

    return None  # Already configured


# Internal: Permission configuration


def _install_permissions(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Configure permissions for agents that need them."""
    if not agent.permissions_file or not agent.permissions_payload:
        return None

    if is_global:
        if agent.config_global_dir:
            config_dir = Path.home() / agent.config_global_dir.lstrip("~/")
        else:
            return None
        perm_path = config_dir / agent.permissions_file
    else:
        if agent.config_local_dir:
            config_dir = project_path / agent.config_local_dir
        else:
            return None
        perm_path = config_dir / agent.permissions_file

    config_dir.mkdir(parents=True, exist_ok=True)

    if perm_path.exists():
        existing = json.loads(perm_path.read_text(encoding="utf-8"))
    else:
        existing = {}

    # Merge permissions
    changed = False
    for key, value in agent.permissions_payload.items():
        if key == "permissions":
            perms = existing.setdefault("permissions", {})
            allow_list = perms.setdefault("allow", [])
            for perm in value.get("allow", []):
                if perm not in allow_list:
                    allow_list.append(perm)
                    changed = True

    if changed:
        perm_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return "Added permissions"

    return None  # Already configured


# Utilities


def _display_path(path: Path, is_global: bool) -> str:
    """Create a display-friendly path string."""
    try:
        if is_global:
            return str(path.relative_to(Path.home()))
        return str(path)
    except ValueError:
        return str(path)

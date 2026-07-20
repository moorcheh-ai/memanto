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

    # Remove hook configuration
    if agent.supports_hooks and agent.hook_config:
        try:
            result = _remove_hooks(agent, project_path, is_global)
            if result:
                steps.append(result)
        except Exception as e:
            errors.append(f"Hook removal: {e}")

    # Remove permissions
    if agent.permissions_file and agent.permissions_payload:
        try:
            result = _remove_permissions(agent, project_path, is_global)
            if result:
                steps.append(result)
        except Exception as e:
            errors.append(f"Permission removal: {e}")

    try:
        ConfigManager().remove_connection(agent_name, project_path, is_global)
    except Exception as e:
        errors.append(f"Registry removal: {e}")

    return {"agent": agent_name, "steps": steps, "errors": errors}

def _remove_hooks(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str:
    # Remove hook configuration from Claude Code settings
    claude_settings_path = project_path / ".claude" / "settings.json"
    if claude_settings_path.exists():
        with open(claude_settings_path, "r+") as f:
            settings = json.load(f)
            # Remove MEMANTO-managed hooks
            settings["hooks"] = [
                hook
                for hook in settings["hooks"]
                if not hook.startswith(MEMANTO_SENTINEL)
            ]
            f.seek(0)
            json.dump(settings, f, indent=4)
            f.truncate()
        return f"Removed MEMANTO-managed hooks from {claude_settings_path}"

    return ""

def _remove_permissions(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str:
    # Remove permissions from Claude Code settings
    claude_settings_path = project_path / ".claude" / "settings.json"
    if claude_settings_path.exists():
        with open(claude_settings_path, "r+") as f:
            settings = json.load(f)
            # Remove MEMANTO-managed permissions
            settings["permissions"] = [
                perm
                for perm in settings["permissions"]
                if not perm.startswith(MEMANTO_SENTINEL)
            ]
            f.seek(0)
            json.dump(settings, f, indent=4)
            f.truncate()
        return f"Removed MEMANTO-managed permissions from {claude_settings_path}"

    return ""
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
    MEMANTO_DYNAMIC_SENTINEL,
    MEMANTO_DYNAMIC_SENTINEL_END,
    MEMANTO_SENTINEL,
    MEMANTO_SENTINEL_END,
    get_extension_content,
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

    # Code extension (Pi .ts extension that runs memanto memory sync on startup)
    if agent.extension_file:
        try:
            ext_result = _install_extension(agent, project_path, is_global)
            if ext_result:
                steps.append(ext_result)
        except Exception as e:
            errors.append(f"Extension: {e}")

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

    # Remove hook configuration (only Claude Code currently)
    if agent.supports_hooks and agent.hook_config:
        try:
            hook_result = _remove_hooks(agent, project_path, is_global)
            if hook_result:
                steps.append(hook_result)
        except Exception as e:
            errors.append(f"Hook removal: {e}")

    # Remove permissions added by MEMANTO
    if agent.permissions_file and agent.permissions_payload:
        try:
            perm_result = _remove_permissions(agent, project_path, is_global)
            if perm_result:
                steps.append(perm_result)
        except Exception as e:
            errors.append(f"Permission removal: {e}")

    # Remove code extension (agent-specific)
    if agent.extension_file:
        try:
            ext_result = _remove_extension(agent, project_path, is_global)
            if ext_result:
                steps.append(ext_result)
        except Exception as e:
            errors.append(f"Extension removal: {e}")

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
    if is_global and not agent.instruction_global_file:
        return None
    if not is_global and not agent.instruction_local_file:
        return None

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


def _strip_dynamic_block(text: str) -> str:
    """Remove the dynamic memory block from the text."""
    return re.sub(
        re.escape(MEMANTO_DYNAMIC_SENTINEL)
        + r".*?"
        + re.escape(MEMANTO_DYNAMIC_SENTINEL_END),
        "",
        text,
        flags=re.DOTALL,
    ).strip()


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
            static_content = _strip_dynamic_block(content)
            updated = re.sub(
                pattern,
                static_content.replace("\\", "\\\\"),
                existing,
                flags=re.DOTALL,
            )
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
            static_section = _strip_dynamic_block(section)
            updated = re.sub(
                pattern,
                static_section.replace("\\", "\\\\"),
                existing,
                flags=re.DOTALL,
            )
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
    instr_path = agent.resolve_instruction_file(project_path, is_global)
    if not instr_path or not instr_path.exists():
        return None

    # For dedicated files (cline, roo, continue, augment, cursor)
    if agent.instruction_is_dir or agent.instruction_format == "mdc":
        try:
            existing = instr_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
        if MEMANTO_SENTINEL not in existing:
            return None
        instr_path.unlink()
        # Clean up empty parent dirs
        parent = instr_path.parent
        try:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            # Ignore errors if directory is not empty or non-deletable
            pass
        return f"Removed {instr_path.name}"

    # For shared files (CLAUDE.md, AGENTS.md, etc.), remove the section
    existing = instr_path.read_text(encoding="utf-8")
    modified = False

    if MEMANTO_SENTINEL in existing:
        pattern = re.escape(MEMANTO_SENTINEL) + r".*?" + re.escape(MEMANTO_SENTINEL_END)
        existing = re.sub(pattern, "", existing, flags=re.DOTALL)
        modified = True

    if MEMANTO_DYNAMIC_SENTINEL in existing:
        pattern2 = (
            re.escape(MEMANTO_DYNAMIC_SENTINEL)
            + r".*?"
            + re.escape(MEMANTO_DYNAMIC_SENTINEL_END)
        )
        existing = re.sub(pattern2, "", existing, flags=re.DOTALL)
        modified = True

    if modified:
        # Clean up extra whitespace
        updated = re.sub(r"\n{3,}", "\n\n", existing).strip() + "\n"
        if updated.strip():
            instr_path.write_text(updated, encoding="utf-8")
            return f"Removed MEMANTO sections from {instr_path.name}"
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

    content = get_skill_content(agent.name)

    skill_path.write_text(content, encoding="utf-8")

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
            # Ignore errors if directory is not empty or non-deletable
            pass
        return f"Removed skill from {_display_path(skill_dir, is_global)}"
    return None


# Internal: Code extension deployment (Pi)


def _install_extension(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Deploy the agent's code extension file (e.g. the Pi .ts extension)."""
    if not agent.extension_file:
        return None

    ext_path = agent.resolve_extension_file(project_path, is_global)
    if not ext_path:
        return None

    ext_path.parent.mkdir(parents=True, exist_ok=True)
    ext_path.write_text(get_extension_content(), encoding="utf-8")

    return f"Deployed extension to {_display_path(ext_path, is_global)}"


def _remove_extension(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Remove the agent's code extension file."""
    if not agent.extension_file:
        return None

    ext_path = agent.resolve_extension_file(project_path, is_global)
    if not ext_path or not ext_path.exists():
        return None

    ext_path.unlink()
    # Clean up empty parent dirs
    try:
        if ext_path.parent.exists() and not any(ext_path.parent.iterdir()):
            ext_path.parent.rmdir()
    except Exception:
        # Ignore errors if directory is not empty or non-deletable
        pass
    return f"Removed extension from {_display_path(ext_path.parent, is_global)}"


# Internal: Hook configuration (Claude Code)


def _is_memanto_hook(hook_group: dict) -> bool:
    """Helper to detect if a hook group belongs to memanto."""
    if not isinstance(hook_group, dict):
        return False
    # Handle single hook dicts (e.g. Cursor: {"command": "python ..."})
    cmd = hook_group.get("command", "")
    if "memanto" in cmd or "notify.py" in cmd or "session_start.py" in cmd:
        return True
    hooks = hook_group.get("hooks", [])
    if isinstance(hooks, list):
        for h in hooks:
            if not isinstance(h, dict):
                continue
            c = h.get("command", "")
            if "memanto" in c or "notify.py" in c or "session_start.py" in c:
                return True
    return False


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

    hooks_section = settings.setdefault("hooks", {})
    changed = False

    # 1. Try to load hooks from assets
    assets_hooks_dir = Path(__file__).parent / "assets" / "hooks"
    asset_file_name = agent.hook_config.asset_file or f"{agent.name}-hooks.json"
    asset_file_path = assets_hooks_dir / asset_file_name

    if assets_hooks_dir.exists() and asset_file_path.exists():
        target_hooks_dir = config_dir / "hooks"
        target_hooks_dir.mkdir(parents=True, exist_ok=True)

        # Copy python scripts
        import shutil

        for py_file in assets_hooks_dir.glob("*.py"):
            shutil.copy2(py_file, target_hooks_dir / py_file.name)

        # Parse and inject JSON
        raw_json = asset_file_path.read_text(encoding="utf-8")
        raw_json = raw_json.replace(
            "${CLAUDE_PLUGIN_ROOT}", str(config_dir).replace("\\", "/")
        )
        raw_json = raw_json.replace(
            "${PLUGIN_ROOT}", str(config_dir).replace("\\", "/")
        )
        raw_json = raw_json.replace(
            "${CLAUDE_PROJECT_DIR}", str(project_path.absolute()).replace("\\", "/")
        )

        asset_hooks_data = json.loads(raw_json)
        asset_hooks = asset_hooks_data.get("hooks", {})

        for event_name, event_payloads in asset_hooks.items():
            target_event = hooks_section.setdefault(event_name, [])
            if not isinstance(target_event, list):
                continue

            for payload in event_payloads:
                if not any(_is_memanto_hook(existing) for existing in target_event):
                    target_event.append(payload)
                    changed = True

        if changed:
            settings_path.write_text(
                json.dumps(settings, indent=2) + "\n", encoding="utf-8"
            )
            return "Installed Memanto hooks and scripts"
        return None

    # 2. Fallback to hardcoded agent payload
    session_start = hooks_section.setdefault("SessionStart", [])
    if not any(_is_memanto_hook(group) for group in session_start):
        session_start.append(agent.hook_config.hook_payload)
        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        return "Added SessionStart hook"

    return None


def _remove_hooks(agent: AgentDef, project_path: Path, is_global: bool) -> str | None:
    """Remove MEMANTO hook configuration for agents that support hooks."""
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

    settings_path = config_dir / agent.hook_config.settings_file
    if not settings_path.exists():
        return None

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks_section = settings.get("hooks")
    if not isinstance(hooks_section, dict):
        return None

    changed = False

    # 1. Remove from all hook events
    empty_events = []
    for event_name, event_payloads in hooks_section.items():
        if not isinstance(event_payloads, list):
            continue

        remaining = [group for group in event_payloads if not _is_memanto_hook(group)]
        if len(remaining) != len(event_payloads):
            hooks_section[event_name] = remaining
            changed = True

        if not remaining:
            empty_events.append(event_name)

    for event_name in empty_events:
        hooks_section.pop(event_name, None)

    if not hooks_section:
        settings.pop("hooks", None)

    # 2. Remove copied script files
    target_hooks_dir = config_dir / "hooks"
    if target_hooks_dir.exists():
        for f in ["notify.py", "session_start.py"]:
            script_path = target_hooks_dir / f
            if script_path.exists():
                try:
                    script_path.unlink()
                except Exception:
                    # Ignore errors if script file cannot be unlinked
                    pass
        # Try to remove dir if empty
        try:
            target_hooks_dir.rmdir()
        except Exception:
            # Ignore errors if directory is not empty or non-deletable
            pass

    if changed:
        _write_or_remove_json(settings_path, settings)
        return "Removed Memanto hooks and scripts"

    return None


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


def _remove_permissions(
    agent: AgentDef, project_path: Path, is_global: bool
) -> str | None:
    """Remove permissions added by MEMANTO without disturbing user entries."""
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

    if not perm_path.exists():
        return None

    existing = json.loads(perm_path.read_text(encoding="utf-8"))
    permissions = existing.get("permissions")
    allow_list = permissions.get("allow") if isinstance(permissions, dict) else None
    if not isinstance(allow_list, list):
        return None

    expected_permissions = set(
        agent.permissions_payload.get("permissions", {}).get("allow", [])
    )
    if not expected_permissions:
        return None

    next_allow = [perm for perm in allow_list if perm not in expected_permissions]
    if len(next_allow) == len(allow_list):
        return None

    if next_allow:
        permissions["allow"] = next_allow
    else:
        permissions.pop("allow", None)
    if isinstance(permissions, dict) and not permissions:
        existing.pop("permissions", None)

    _write_or_remove_json(perm_path, existing)
    return "Removed permissions"


# Utilities


def _display_path(path: Path, is_global: bool) -> str:
    """Create a display-friendly path string."""
    try:
        if is_global:
            return str(path.relative_to(Path.home()))
        return str(path)
    except ValueError:
        return str(path)


def _write_or_remove_json(path: Path, data: dict[str, Any]) -> None:
    """Persist JSON data, or remove the file when the managed data was all it had."""
    if data:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return

    path.unlink()
    parent = path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except (FileNotFoundError, OSError):
        # Best-effort cleanup: parent may be removed/changed concurrently or be non-removable.
        pass

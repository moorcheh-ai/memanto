import os
import re
import stat
from pathlib import Path
from typing import Any

from memanto.cli.connect.agent_registry import list_agents
from memanto.cli.connect.engine import install_agent
from memanto.cli.connect.templates import TEMPLATE_VERSION


def _extract_version(file_path: Path) -> str | None:
    """Extracts the memanto template version from a file."""
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
        match = re.search(r"<!-- memanto-template-version: ([\d\.]+) -->", content)
        if match:
            v_str = match.group(1)
            try:
                # Validate all components are integers to prevent malformed versions like 1..2
                [int(x) for x in v_str.split(".")]
                return v_str
            except ValueError:
                # Ignore version string if parts are not valid integers
                pass

        if "<!-- MEMANTO-MANAGED-SECTION -->" in content:
            return "0.0.0"
        return None
    except Exception:
        return None


def _is_version_lower(v1: str, v2: str) -> bool:
    """Simple semver comparison."""
    try:
        return [int(x) for x in v1.split(".")] < [int(x) for x in v2.split(".")]
    except ValueError:
        return False


def check_for_updates(
    project_dir: str = ".",
) -> dict[str, Any]:
    """
    Scans the workspace and globally for active integrations and checks if their templates are outdated.

    Returns:
        dict: {
            "outdated": bool,
            "installed_version": str | None,
            "latest_version": str,
            "active_agents": list[str],
            "active_local": list[str],
            "active_global": list[str]
        }
    """
    project_path = Path(project_dir).expanduser().resolve()
    lowest_version = None
    active_local = []
    active_global = []

    for agent in list_agents():
        # Check Local
        local_has_files = False
        inst_path_local = agent.resolve_instruction_file(project_path, False)
        if inst_path_local and inst_path_local.exists():
            v = _extract_version(inst_path_local)
            if v is not None:
                local_has_files = True
                if lowest_version is None or _is_version_lower(v, lowest_version):
                    lowest_version = v

        skill_dir_local = agent.resolve_skill_local(project_path)
        skill_path_local = skill_dir_local / "SKILL.md"
        if skill_path_local.exists():
            v = _extract_version(skill_path_local)
            if v is not None:
                local_has_files = True
                if lowest_version is None or _is_version_lower(v, lowest_version):
                    lowest_version = v

        if local_has_files:
            active_local.append(agent.name)

        # Check Global
        global_has_files = False
        inst_path_global = agent.resolve_instruction_file(project_path, True)
        if inst_path_global and inst_path_global.exists():
            v = _extract_version(inst_path_global)
            if v is not None:
                global_has_files = True
                if lowest_version is None or _is_version_lower(v, lowest_version):
                    lowest_version = v

        skill_dir_global = agent.resolve_skill_global()
        skill_path_global = skill_dir_global / "SKILL.md"
        if skill_path_global.exists():
            v = _extract_version(skill_path_global)
            if v is not None:
                global_has_files = True
                if lowest_version is None or _is_version_lower(v, lowest_version):
                    lowest_version = v

        if global_has_files:
            active_global.append(agent.name)

    is_outdated = False
    if lowest_version and _is_version_lower(lowest_version, TEMPLATE_VERSION):
        is_outdated = True

    return {
        "outdated": is_outdated,
        "installed_version": lowest_version,
        "latest_version": TEMPLATE_VERSION,
        "active_agents": list(set(active_local + active_global)),
        "active_local": active_local,
        "active_global": active_global,
    }


def update_all_agents(
    project_dir: str = ".", update_global: bool = True, update_local: bool = True
) -> list[str]:
    """
    Updates all currently installed agents to the latest template version.
    Returns a list of messages.
    """
    status = check_for_updates(project_dir)
    messages = []

    if not status.get("active_local") and not status.get("active_global"):
        return ["No active Memanto integrations found to update."]

    has_errors = False
    ran_updates = False

    if update_local:
        for agent_name in status.get("active_local", []):
            ran_updates = True
            res = install_agent(agent_name, project_dir, is_global=False)
            messages.extend(res.get("steps", []))
            if res.get("errors"):
                has_errors = True
                messages.extend(
                    [f"Error updating local {agent_name}: {e}" for e in res["errors"]]
                )

    if update_global:
        for agent_name in status.get("active_global", []):
            ran_updates = True
            res = install_agent(agent_name, project_dir, is_global=True)
            messages.extend(res.get("steps", []))
            if res.get("errors"):
                has_errors = True
                messages.extend(
                    [f"Error updating global {agent_name}: {e}" for e in res["errors"]]
                )

    if not ran_updates:
        return ["No active Memanto integrations found in the selected scope."]

    if not has_errors:
        messages.append(
            f"\n🎉 Successfully updated all active agent instructions to v{TEMPLATE_VERSION}!"
        )
    else:
        messages.append(
            "\n⚠️ Update completed with errors. Some instructions may not have been updated."
        )

    return messages


def _assert_dynamic_sync_write_scope(
    project_path: Path, target: Path, is_global: bool
) -> Path:
    """Return the resolved target after enforcing project-local write scope."""
    try:
        root = project_path.resolve()
        resolved = target.resolve(strict=False)
        if not is_global:
            resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"Refusing dynamic memory sync outside project: {target}"
        ) from exc

    return resolved


def _open_local_dynamic_sync_file(project_path: Path, target: Path) -> int:
    """Open a project-local target through one no-follow directory chain."""
    root = project_path.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Refusing dynamic memory sync outside project: {target}"
        ) from exc

    if not relative.parts:
        raise ValueError(f"Refusing dynamic memory sync to project directory: {target}")

    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in supports_dir_fd
    ):
        raise ValueError(
            "Secure local dynamic memory sync requires no-follow dir_fd support"
        )

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(root, directory_flags)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd

        file_fd = os.open(
            relative.parts[-1],
            os.O_RDWR | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
    finally:
        os.close(directory_fd)

    if not stat.S_ISREG(os.fstat(file_fd).st_mode):
        os.close(file_fd)
        raise ValueError(f"Refusing dynamic memory sync to non-regular file: {target}")
    return file_fd


def inject_dynamic_memories(
    project_dir: str,
    content: str,
    connection: str | None = None,
    scope: str | None = None,
) -> dict[str, list[str]]:
    """Write ``content`` into the dynamic memory section of connected agents.

    Targets the named ``connection``, or every connection that applies to
    ``project_dir`` for the requested ``scope`` (``"local"``, ``"global"``,
    or local connections first and global ones as a fallback when omitted).
    Only the text between the Memanto dynamic sentinels in each agent's
    instruction file and ``SKILL.md`` is replaced. Local writes must stay
    inside the project and go through a no-follow descriptor chain.

    Returns messages grouped under ``updated``, ``already_current`` and
    ``no_eligible_target``. Raises ``ValueError`` for an invalid scope, when
    no connection applies, or when a target falls outside the allowed scope.
    """
    from memanto.cli.config.manager import ConfigManager
    from memanto.cli.connect.agent_registry import get_agent
    from memanto.cli.connect.templates import (
        MEMANTO_DYNAMIC_SENTINEL,
        MEMANTO_DYNAMIC_SENTINEL_END,
    )

    project_path = Path(project_dir).expanduser().resolve()
    results: dict[str, list[str]] = {
        "updated": [],
        "already_current": [],
        "no_eligible_target": [],
    }

    pattern = re.compile(
        rf"({re.escape(MEMANTO_DYNAMIC_SENTINEL)}).*?({re.escape(MEMANTO_DYNAMIC_SENTINEL_END)})",
        flags=re.DOTALL,
    )

    if scope not in (None, "local", "global"):
        raise ValueError("scope must be one of: local, global")

    connections = ConfigManager().load_connections()

    if connection:
        target_connections = [connection]
    else:
        target_connections = []
        if scope == "local":
            target_connections = [
                name
                for name, entry in connections.items()
                if str(project_path) in entry.get("projects", [])
            ]
        elif scope == "global":
            target_connections = [
                name
                for name, entry in connections.items()
                if entry.get("installed_global")
            ]
        else:
            target_connections = [
                name
                for name, entry in connections.items()
                if str(project_path) in entry.get("projects", [])
            ]
            if not target_connections:
                target_connections = [
                    name
                    for name, entry in connections.items()
                    if entry.get("installed_global")
                ]

        if not target_connections:
            raise ValueError(
                f"No Memanto connections found for {project_path}. "
                "Run 'memanto connect' first."
            )

    for conn_name in target_connections:
        agent = get_agent(conn_name)
        entry = connections.get(conn_name)
        if agent is None or not isinstance(entry, dict):
            if connection:
                raise ValueError(f"No Memanto connection registered for '{conn_name}'.")
            continue

        has_local = str(project_path) in entry.get("projects", [])
        has_global = bool(entry.get("installed_global"))

        if scope == "local":
            if not has_local:
                if connection:
                    raise ValueError(
                        f"No local '{conn_name}' connection for {project_path}."
                    )
                continue
            is_global = False
        elif scope == "global":
            if not has_global:
                if connection:
                    raise ValueError(
                        f"No global '{conn_name}' connection is registered."
                    )
                continue
            is_global = True
        elif has_local:
            is_global = False
        elif has_global:
            is_global = True
        else:
            if connection:
                raise ValueError(
                    f"No '{conn_name}' connection applies to {project_path}."
                )
            continue

        instruction_path = agent.resolve_instruction_file(project_path, is_global)
        skill_dir = (
            agent.resolve_skill_global()
            if is_global
            else agent.resolve_skill_local(project_path)
        )
        paths_to_check = [
            instruction_path,
            skill_dir / "SKILL.md" if skill_dir else None,
        ]

        for path in paths_to_check:
            if path and path.exists():
                resolved_path = _assert_dynamic_sync_write_scope(
                    project_path, path, is_global
                )
                # Global scope intentionally keeps its existing path behavior. Local
                # scope binds the entire directory walk and final file to descriptors,
                # then reuses the same final descriptor for read/truncate/write.
                local_handle = None
                if is_global:
                    text = resolved_path.read_text(encoding="utf-8")
                else:
                    file_fd = _open_local_dynamic_sync_file(project_path, resolved_path)
                    local_handle = os.fdopen(file_fd, "r+", encoding="utf-8")
                    try:
                        text = local_handle.read()
                    except Exception:
                        local_handle.close()
                        raise

                try:
                    if MEMANTO_DYNAMIC_SENTINEL in text:

                        def replacer(match):
                            """Replace one sentinel block's body with ``content``, minus any sentinels."""
                            if content:
                                safe_content = content.replace(
                                    MEMANTO_DYNAMIC_SENTINEL, ""
                                ).replace(MEMANTO_DYNAMIC_SENTINEL_END, "")
                                return f"{match.group(1)}\n{safe_content}\n{match.group(2)}"
                            return f"{match.group(1)}\n{match.group(2)}"

                        new_text = pattern.sub(replacer, text)
                        if new_text != text:
                            if is_global:
                                resolved_path.write_text(new_text, encoding="utf-8")
                            else:
                                assert local_handle is not None
                                local_handle.seek(0)
                                local_handle.write(new_text)
                                local_handle.truncate()
                                local_handle.flush()
                            results["updated"].append(
                                f"Injected memories into {path.name} ({agent.name}, "
                                f"{'global' if is_global else 'local'})"
                            )
                        else:
                            results["already_current"].append(
                                f"{path.name} ({agent.name}) is already current"
                            )
                    else:
                        results["no_eligible_target"].append(
                            f"{path.name} ({agent.name}) has no dynamic section"
                        )
                finally:
                    if local_handle is not None:
                        local_handle.close()

    return results

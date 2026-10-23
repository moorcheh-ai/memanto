"""
MEMANTO CLI - MCP server setup for `memanto connect`

Registers the memanto MCP server (memanto-mcp) with clients that support it,
so the agent gets `remember` / `recall` as native tools instead of having to
run CLI commands from instruction text.

The API key is never written into any client config: memanto-mcp reads it from
~/.memanto/.env, where `memanto` already stores it. Entries written here carry
a marker so `memanto connect remove` only ever removes what connect added, and
an entry the user configured by hand is left untouched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "memanto"
MANAGED_ENV = "MEMANTO_MANAGED_BY"
MANAGED_VALUE = "memanto-connect"
CLAUDE_TOOL_PERMISSION = "mcp__memanto"

CODEX_BLOCK_START = "# >>> memanto (managed by `memanto connect`)"
CODEX_BLOCK_END = "# <<< memanto"
_CODEX_BLOCK_RE = re.compile(
    re.escape(CODEX_BLOCK_START) + r".*?" + re.escape(CODEX_BLOCK_END) + r"\n?",
    re.DOTALL,
)
CODEX_ENV_VARS = (
    "USERPROFILE",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
)
_CODEX_SERVER_RE = re.compile(r"(?m)^\s*\[mcp_servers\.memanto(\]|\.)")


def server_command() -> tuple[str, list[str]] | None:
    """How clients should start memanto-mcp, or None if it isn't installed."""
    # Store the resolved path: clients often start servers with a different
    # PATH than the shell running connect (GUI-launched Cursor, Codex).
    resolved = shutil.which("memanto-mcp")
    if resolved:
        return str(Path(resolved).resolve()), []
    if importlib.util.find_spec("memanto_mcp") is not None:
        return sys.executable, ["-m", "memanto_mcp"]
    return None


def _server_entry(
    command: str, args: list[str], agent_id: str, client: str = ""
) -> dict[str, Any]:
    env = {"MEMANTO_DEFAULT_AGENT_ID": agent_id, MANAGED_ENV: MANAGED_VALUE}
    if client:
        # Override the default source in the MCP server with the CLI client name
        # so cross-namespace setups (e.g. Cursor writing to Copilot namespace)
        # attribute the write to the actual client making the call.
        env["MEMANTO_DEFAULT_SOURCE"] = client
    return {
        "command": command,
        "args": args,
        "env": env,
    }


def _is_managed(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("env"), dict)
        and entry["env"].get(MANAGED_ENV) == MANAGED_VALUE
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def _check_local(project_path: Path, target: Path, is_global: bool) -> None:
    """Same fail-closed project-root check the rest of connect uses."""
    from memanto.cli.connect.engine import _assert_local_write_scope

    _assert_local_write_scope(project_path, target, is_global)


def _vscode_user_mcp_path() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
        return Path(base) / "Code" / "User" / "mcp.json"
    elif sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "mcp.json"
        )
    else:
        return Path.home() / ".config" / "Code" / "User" / "mcp.json"


# JSON clients (Claude Code .mcp.json / ~/.claude.json, Cursor mcp.json, VS Code mcp.json)


def _install_json_server(
    path: Path, servers_key: str, entry: dict[str, Any]
) -> str | None:
    data = _read_json(path)
    servers = data.setdefault(servers_key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"'{servers_key}' in {path} is not an object")
    existing = servers.get(SERVER_NAME)
    if existing is not None and not _is_managed(existing):
        return f"Kept your existing '{SERVER_NAME}' MCP server in {path.name}"
    if existing == entry:
        return None
    servers[SERVER_NAME] = entry
    _write_json(path, data)
    return f"Added memanto MCP server to {path.name}"


def _remove_json_server(path: Path, servers_key: str) -> str | None:
    if not path.exists():
        return None
    data = _read_json(path)
    servers = data.get(servers_key)
    if not isinstance(servers, dict) or not _is_managed(servers.get(SERVER_NAME)):
        return None
    del servers[SERVER_NAME]
    if not servers:
        data.pop(servers_key, None)
    _write_json(path, data)
    return f"Removed memanto MCP server from {path.name}"


def _claude_enable_project_server(settings_path: Path, enable: bool) -> None:
    """Pre-approve (or un-approve) the project .mcp.json server for Claude Code."""
    data = _read_json(settings_path)
    enabled = data.get("enabledMcpjsonServers")
    enabled = enabled if isinstance(enabled, list) else []
    if enable and SERVER_NAME not in enabled:
        data["enabledMcpjsonServers"] = [*enabled, SERVER_NAME]
    elif not enable and SERVER_NAME in enabled:
        rest = [name for name in enabled if name != SERVER_NAME]
        if rest:
            data["enabledMcpjsonServers"] = rest
        else:
            data.pop("enabledMcpjsonServers", None)
    else:
        return
    _write_json(settings_path, data)


# Codex (~/.codex/config.toml)


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _toml_str(value: str) -> str:
    # JSON string escaping is valid for TOML basic strings.
    return json.dumps(value)


def _install_codex(command: str, args: list[str], agent_id: str) -> str | None:
    path = _codex_config_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    outside = _CODEX_BLOCK_RE.sub("", text)
    if _CODEX_SERVER_RE.search(outside):
        return "Kept your existing 'memanto' MCP server in ~/.codex/config.toml"
    block = "\n".join(
        [
            CODEX_BLOCK_START,
            f"[mcp_servers.{SERVER_NAME}]",
            f"command = {_toml_str(command)}",
            f"args = [{', '.join(_toml_str(a) for a in args)}]",
            # Run memanto tools without an approval prompt for each call.
            'default_tools_approval_mode = "approve"',
            # Codex starts MCP servers with a minimal environment; without the
            # home variables memanto-mcp can't find ~/.memanto/.env (the key)
            # and Codex silently drops the server's tools.
            f"env_vars = [{', '.join(_toml_str(v) for v in CODEX_ENV_VARS)}]",
            "",
            f"[mcp_servers.{SERVER_NAME}.env]",
            f"MEMANTO_DEFAULT_AGENT_ID = {_toml_str(agent_id)}",
            f"{MANAGED_ENV} = {_toml_str(MANAGED_VALUE)}",
            CODEX_BLOCK_END,
            "",
        ]
    )
    if _CODEX_BLOCK_RE.search(text):
        new_text = _CODEX_BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        base = text if not text or text.endswith("\n") else text + "\n"
        new_text = base + ("\n" if base else "") + block
    if new_text == text:
        return None
    old_block = _CODEX_BLOCK_RE.search(text)
    old_agent = (
        re.search(r'MEMANTO_DEFAULT_AGENT_ID = "([^"]*)"', old_block.group(0))
        if old_block
        else None
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    if old_agent and old_agent.group(1) != agent_id:
        return (
            "Updated memanto MCP server in ~/.codex/config.toml: agent changed from "
            f"'{old_agent.group(1)}' to '{agent_id}' for every Codex project"
        )
    return "Added memanto MCP server to ~/.codex/config.toml"


def _remove_codex() -> str | None:
    path = _codex_config_path()
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not _CODEX_BLOCK_RE.search(text):
        return None
    new_text = _CODEX_BLOCK_RE.sub("", text).rstrip("\n")
    path.write_text(new_text + "\n" if new_text else "", encoding="utf-8")
    return "Removed memanto MCP server from ~/.codex/config.toml"


# Public entry points


def install_mcp(
    client: str, project_path: Path, is_global: bool, agent_id: str | None
) -> str | None:
    """Register memanto-mcp for one client. Returns a step message or None."""
    launch = server_command()
    if launch is None:
        return (
            "Skipped MCP server: memanto-mcp is not installed "
            "(pip install memanto-mcp, then run connect again)"
        )
    if not agent_id:
        return (
            "Skipped MCP server: no active memanto agent provided "
            "(pass an agent ID to connect, or activate one first)"
        )
    command, args = launch
    # Pass the CLI client identifier so the MCP server knows who configured it
    # and can use it as the default source when writing memories.
    entry = _server_entry(command, args, agent_id, client)

    if client == "claude":
        if is_global:
            return _install_json_server(
                Path.home() / ".claude.json", "mcpServers", entry
            )
        mcp_json = project_path / ".mcp.json"
        settings = project_path / ".claude" / "settings.local.json"
        _check_local(project_path, mcp_json, is_global)
        _check_local(project_path, settings, is_global)
        result = _install_json_server(mcp_json, "mcpServers", entry)
        # Only pre-approve the entry connect owns, never a user's own server.
        if result is None or not result.startswith("Kept"):
            _claude_enable_project_server(settings, enable=True)
        return result
    if client == "cursor":
        base = Path.home() if is_global else project_path
        target = base / ".cursor" / "mcp.json"
        _check_local(project_path, target, is_global)
        return _install_json_server(target, "mcpServers", entry)
    if client == "github-copilot":
        target = (
            _vscode_user_mcp_path()
            if is_global
            else project_path / ".vscode" / "mcp.json"
        )
        _check_local(project_path, target, is_global)
        entry["type"] = "stdio"
        return _install_json_server(target, "servers", entry)
    if client == "codex":
        # Codex reads MCP servers only from the user config, for every project.
        return _install_codex(command, args, agent_id)
    raise ValueError(f"Unknown MCP client: {client}")


def remove_mcp(client: str, project_path: Path, is_global: bool) -> str | None:
    """Remove the memanto-mcp entry connect added. Returns a step message or None."""
    if client == "claude":
        if is_global:
            return _remove_json_server(Path.home() / ".claude.json", "mcpServers")
        mcp_json = project_path / ".mcp.json"
        settings = project_path / ".claude" / "settings.local.json"
        _check_local(project_path, mcp_json, is_global)
        _check_local(project_path, settings, is_global)
        result = _remove_json_server(mcp_json, "mcpServers")
        # Only withdraw the approval when connect's own entry was removed.
        if result and settings.exists():
            _claude_enable_project_server(settings, enable=False)
        return result
    if client == "cursor":
        base = Path.home() if is_global else project_path
        target = base / ".cursor" / "mcp.json"
        _check_local(project_path, target, is_global)
        return _remove_json_server(target, "mcpServers")
    if client == "github-copilot":
        target = (
            _vscode_user_mcp_path()
            if is_global
            else project_path / ".vscode" / "mcp.json"
        )
        _check_local(project_path, target, is_global)
        return _remove_json_server(target, "servers")
    if client == "codex":
        # The Codex entry is shared by every project, so only a global remove
        # takes it out; removing one project must not break the others.
        return _remove_codex() if is_global else None
    raise ValueError(f"Unknown MCP client: {client}")

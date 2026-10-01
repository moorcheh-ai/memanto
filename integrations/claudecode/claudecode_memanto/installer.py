"""Compatibility helpers that delegate to the core Claude Code integration."""

from memanto.cli.connect.engine import install_agent, remove_agent


def install_hooks(global_scope: bool = False) -> int:
    """Install the same Claude Code integration as ``memanto connect``."""
    result = install_agent("claude-code", is_global=global_scope)
    return 1 if result["errors"] else 0


def uninstall_hooks(global_scope: bool = False) -> int:
    """Remove the same Claude Code integration as ``memanto connect``."""
    result = remove_agent("claude-code", is_global=global_scope)
    return 1 if result["errors"] else 0

"""Memanto MCP Server.

Exposes Memanto's persistent semantic memory as Model Context Protocol tools
so any MCP-compatible agent (Claude Desktop, Cursor, Windsurf, Cline, etc.)
can store and retrieve long-term memory.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.server import build_server, run_server

__all__ = ["MCPServerSettings", "build_server", "run_server", "__version__"]

try:
    # Read the installed distribution rather than restating the version here:
    # a hardcoded literal silently reports a stale number when pyproject is
    # bumped for a release (0.1.1 shipped announcing itself as 0.1.0).
    __version__ = version("memanto-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0.dev0"

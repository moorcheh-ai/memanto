"""Memanto MCP Server.

Exposes Memanto's persistent semantic memory as Model Context Protocol tools
so any MCP-compatible agent (Claude Desktop, Cursor, Windsurf, Cline, etc.)
can store and retrieve long-term memory.
"""

from __future__ import annotations

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.server import build_server, run_server

__all__ = ["MCPServerSettings", "build_server", "run_server", "__version__"]
__version__ = "0.1.0"

"""FastMCP server assembly and transport runner.

Builds a fully configured ``FastMCP`` instance with every Memanto tool
registered, then dispatches to the requested transport.

Logging is routed to **stderr only** because stdio MCP clients use stdout
exclusively for JSON-RPC frames - anything written there breaks the protocol.
"""

from __future__ import annotations

import logging
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - install-time message
    raise ImportError(
        "memanto-mcp requires the `mcp` package. Install with: pip install 'mcp[cli]>=1.2'"
    ) from exc

from memanto_mcp.config import MCPServerSettings, TransportType
from memanto_mcp.lifecycle import MemantoLifecycle
from memanto_mcp.tools import register_tools

logger = logging.getLogger("memanto_mcp")


def _configure_logging(level: str) -> None:
    """Send every log line to stderr - stdout is reserved for MCP frames."""
    root = logging.getLogger()
    # Drop any handlers another importer may have attached to root (e.g.
    # a parent CLI). They might point at stdout, which would corrupt JSON-RPC.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet a few noisy third-party loggers that don't add value at INFO.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


def build_server(settings: MCPServerSettings | None = None) -> FastMCP:
    """Construct a FastMCP server with all Memanto tools wired up.

    Returned without being run, so callers (tests, custom hosts) can mount
    additional tools or inspect the schema before serving.
    """
    settings = settings or MCPServerSettings()  # type: ignore[call-arg]
    _configure_logging(settings.log_level)

    instructions = (
        "Memanto provides persistent semantic memory for AI agents. Use "
        "`recall` (or `answer` for RAG) BEFORE asking the user to repeat "
        "stable facts, preferences, or prior decisions - the answer may "
        "already be in memory. After learning something new and durable, "
        "use `remember` (or `batch_remember`) to persist it for future "
        "sessions. Pass a fresh, well-phrased natural-language query to "
        "`recall`; do not pass keyword fragments."
    )

    mcp = FastMCP(
        name="memanto",
        instructions=instructions,
        host=settings.host,
        port=settings.port,
    )

    lifecycle = MemantoLifecycle(settings)
    register_tools(mcp, lifecycle)

    # Stash on the server object so transport runners / tests can reach it.
    mcp._memanto_lifecycle = lifecycle  # type: ignore[attr-defined]
    mcp._memanto_settings = settings  # type: ignore[attr-defined]

    logger.info(
        "Memanto MCP server ready (transport=%s, default_agent=%s, admin_tools=%s)",
        settings.transport.value,
        settings.default_agent_id or "<none>",
        settings.expose_admin_tools,
    )
    return mcp


def run_server(settings: MCPServerSettings | None = None) -> None:
    """Build the server and serve over the configured transport."""
    mcp = build_server(settings)
    settings = mcp._memanto_settings  # type: ignore[attr-defined]
    lifecycle: MemantoLifecycle = mcp._memanto_lifecycle  # type: ignore[attr-defined]

    transport = settings.transport
    try:
        if transport is TransportType.STDIO:
            # FastMCP.run() defaults to stdio when called with no transport.
            mcp.run(transport="stdio")
        elif transport is TransportType.SSE:
            mcp.run(transport="sse")
        elif transport is TransportType.STREAMABLE_HTTP:
            mcp.run(transport="streamable-http")
        else:  # pragma: no cover - exhausted by enum
            raise ValueError(f"Unsupported transport: {transport}")
    finally:
        lifecycle.shutdown()

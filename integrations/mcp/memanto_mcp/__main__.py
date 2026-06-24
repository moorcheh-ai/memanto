"""Module entrypoint: ``python -m memanto_mcp``.

Equivalent to the ``memanto-mcp`` console script declared in pyproject.toml.
"""

from __future__ import annotations

import argparse
import logging
import sys

from memanto_mcp.config import MCPServerSettings, TransportType
from memanto_mcp.server import run_server


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memanto-mcp",
        description=(
            "Memanto MCP server - exposes Memanto's persistent semantic memory "
            "(remember, recall, answer) as Model Context Protocol tools."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        help=(
            "Transport to use. Defaults to stdio (the standard for desktop "
            "MCP clients like Claude Desktop / Cursor). Use sse or "
            "streamable-http for remote/HTTP clients."
        ),
    )
    parser.add_argument(
        "--host",
        help="Bind host for sse/streamable-http transports (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Bind port for sse/streamable-http transports (default: 8765).",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Log level (default: INFO). Logs are always written to stderr.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.version:
        from memanto_mcp import __version__

        print(__version__)
        return 0

    overrides: dict[str, object] = {}
    if args.transport:
        overrides["transport"] = TransportType(args.transport)
    if args.host:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.log_level:
        overrides["log_level"] = args.log_level

    try:
        settings = MCPServerSettings(**overrides)  # type: ignore[arg-type]
    except Exception as exc:
        # Print a clear actionable error to stderr - do NOT pollute stdout in
        # stdio mode (it is reserved for JSON-RPC frames).
        print(f"memanto-mcp: configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        run_server(settings)
    except KeyboardInterrupt:
        logging.getLogger("memanto_mcp").info("Shutting down (KeyboardInterrupt)")
        return 0
    except Exception as exc:
        logging.getLogger("memanto_mcp").exception("Fatal error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

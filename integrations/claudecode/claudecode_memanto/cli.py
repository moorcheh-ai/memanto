"""``claudecode-memanto`` CLI wrapper for the core Memanto integration."""

from __future__ import annotations

import argparse

from memanto.cli.connect.engine import install_agent, remove_agent


def main(argv: list[str] | None = None) -> int:
    """Install or remove the core Claude Code integration."""
    parser = argparse.ArgumentParser(
        prog="claudecode-memanto",
        description="Install the Memanto integration for Claude Code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Install the Memanto integration.")
    p_install.add_argument(
        "-p",
        "--project-dir",
        default=".",
        help="Target project directory (default: current directory).",
    )
    p_install.add_argument(
        "-g",
        "--global",
        dest="global_scope",
        action="store_true",
        help="Install globally into ~/.claude/ and ~/.claude.json instead of the current project.",
    )
    p_install.add_argument(
        "-a",
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Default Memanto agent ID to use for the MCP server (defaults to the active agent).",
    )

    p_uninstall = sub.add_parser("uninstall", help="Remove the Memanto integration.")
    p_uninstall.add_argument(
        "-p",
        "--project-dir",
        default=".",
        help="Target project directory (default: current directory).",
    )
    p_uninstall.add_argument(
        "-g",
        "--global",
        dest="global_scope",
        action="store_true",
        help="Uninstall from ~/.claude/ and ~/.claude.json instead of the current project.",
    )

    args = parser.parse_args(argv)

    result = (
        install_agent(
            "claude-code",
            project_dir=args.project_dir,
            is_global=args.global_scope,
            mcp_agent_id=args.agent_id,
        )
        if args.command == "install"
        else remove_agent(
            "claude-code",
            project_dir=args.project_dir,
            is_global=args.global_scope,
        )
    )
    for step in result["steps"]:
        print(step)
    for error in result["errors"]:
        print(f"error: {error}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

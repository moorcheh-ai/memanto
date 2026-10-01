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
        "--global",
        dest="global_scope",
        action="store_true",
        help="Install into ~/.claude/settings.json instead of ./.claude/settings.json.",
    )

    p_uninstall = sub.add_parser("uninstall", help="Remove the Memanto integration.")
    p_uninstall.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="Uninstall from ~/.claude/settings.json instead of ./.claude/settings.json.",
    )

    args = parser.parse_args(argv)

    result = (
        install_agent("claude-code", is_global=args.global_scope)
        if args.command == "install"
        else remove_agent("claude-code", is_global=args.global_scope)
    )
    for step in result["steps"]:
        print(step)
    for error in result["errors"]:
        print(f"error: {error}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

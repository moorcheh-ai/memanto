#!/usr/bin/env python3
"""Helper commands for using Memanto from coding-agent skills.

The script intentionally shells out to the public `memanto` CLI instead of
importing internal modules so it works from a source checkout, an installed
package, or a copied skill pack.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MemoryCommand:
    args: list[str]

    def display(self) -> str:
        return " ".join(shlex.quote(part) for part in self.args)


def run_or_preview(command: MemoryCommand, dry_run: bool) -> int:
    if dry_run:
        print(command.display())
        return 0
    completed = subprocess.run(command.args, check=False)
    return completed.returncode


def setup_command(args: argparse.Namespace) -> MemoryCommand:
    return MemoryCommand(
        [
            "memanto",
            "agent",
            "create",
            args.agent_id,
            "--pattern",
            args.pattern,
            "--description",
            args.description,
        ]
    )


def remember_command(args: argparse.Namespace, memory_type: str) -> MemoryCommand:
    tags = args.tags or f"skills,{memory_type}"
    return MemoryCommand(
        [
            "memanto",
            "remember",
            args.content,
            "--type",
            memory_type,
            "--title",
            args.title,
            "--confidence",
            str(args.confidence),
            "--provenance",
            args.provenance,
            "--source",
            args.source,
            "--tags",
            tags,
        ]
    )


def recall_command(args: argparse.Namespace) -> MemoryCommand:
    return MemoryCommand(
        [
            "memanto",
            "recall",
            args.query,
            "--limit",
            str(args.limit),
        ]
    )


def add_common_remember_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True, help="Short memory title")
    parser.add_argument("--content", required=True, help="Durable memory content")
    parser.add_argument("--tags", default=None, help="Comma-separated tags")
    parser.add_argument("--source", default="claude-code-skill", help="Memory source")
    parser.add_argument("--confidence", type=float, default=0.85, help="0.0-1.0")
    parser.add_argument(
        "--provenance",
        default="explicit_statement",
        help="Memory provenance, e.g. explicit_statement, inferred, corrected",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print command only")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Use Memanto from Claude Code / mattpocock-style skills."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Create and activate a Memanto agent")
    setup.add_argument("--agent-id", required=True)
    setup.add_argument("--pattern", default="project", choices=("project", "support", "tool"))
    setup.add_argument(
        "--description",
        default="Project memory namespace for coding-agent skills",
    )
    setup.add_argument("--dry-run", action="store_true", help="Print command only")

    decision = subparsers.add_parser("remember-decision", help="Store a decision")
    add_common_remember_args(decision)

    error = subparsers.add_parser("remember-error", help="Store a debugging lesson")
    add_common_remember_args(error)

    learning = subparsers.add_parser("remember-learning", help="Store a reusable lesson")
    add_common_remember_args(learning)

    recall = subparsers.add_parser("recall", help="Recall project memory")
    recall.add_argument("--query", required=True)
    recall.add_argument("--limit", type=int, default=5)
    recall.add_argument("--dry-run", action="store_true", help="Print command only")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "setup":
        return run_or_preview(setup_command(args), args.dry_run)
    if args.command == "remember-decision":
        return run_or_preview(remember_command(args, "decision"), args.dry_run)
    if args.command == "remember-error":
        return run_or_preview(remember_command(args, "error"), args.dry_run)
    if args.command == "remember-learning":
        return run_or_preview(remember_command(args, "learning"), args.dry_run)
    if args.command == "recall":
        return run_or_preview(recall_command(args), args.dry_run)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

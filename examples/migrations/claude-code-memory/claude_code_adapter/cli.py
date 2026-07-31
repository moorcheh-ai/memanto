"""Command-line entry point for the Claude Code memory adapter.

Usage examples:

    # Convert one Claude Code session archive to an OKF bundle
    python -m claude_code_adapter.cli --archive ~/.claude/projects/foo/session.jsonl

    # Convert every archive under a Claude projects directory
    python -m claude_code_adapter.cli --projects ~/.claude/projects

    # Skip assistant-derived memories (user statements only)
    python -m claude_code_adapter.cli --archive session.jsonl --user-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_code_adapter.parser import (
    iter_project_archives,
    parse_claude_jsonl,
)
from claude_code_adapter.extractor import extract_memories
from claude_code_adapter.okf_writer import write_okf_bundle


def _collect_turns(args: argparse.Namespace) -> tuple[list, list[str]]:
    """Parse archives from CLI args, returning (turns, sources)."""
    turns: list = []
    sources: list[str] = []

    if args.archive:
        path = Path(args.archive)
        turns.extend(parse_claude_jsonl(path))
        sources.append(str(path))

    if args.projects:
        for archive in iter_project_archives(args.projects):
            turns.extend(parse_claude_jsonl(archive))
            sources.append(str(archive))

    if not turns:
        print("No conversation turns found. Check --archive / --projects paths.", file=sys.stderr)
        sys.exit(1)

    return turns, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        help="Path to a single Claude Code .jsonl session archive",
    )
    parser.add_argument(
        "--projects",
        help="Path to a Claude projects dir (scans *.jsonl recursively)",
    )
    parser.add_argument(
        "--output",
        default="okf_bundle",
        help="Output OKF bundle directory (default: okf_bundle)",
    )
    parser.add_argument(
        "--user-only",
        action="store_true",
        help="Extract user-statement memories only (skip assistant summaries)",
    )
    parser.add_argument(
        "--title",
        default="Claude Code memory bundle",
        help="Title used in the bundle index",
    )
    args = parser.parse_args(argv)

    if not args.archive and not args.projects:
        parser.error("Provide --archive and/or --projects")

    turns, sources = _collect_turns(args)
    print(f"Parsed {len(turns)} conversation turns from {len(sources)} archive(s).")

    memories = extract_memories(
        turns,
        source_path=";".join(sources) if len(sources) > 1 else sources[0],
        include_assistant=not args.user_only,
    )
    print(f"Extracted {len(memories)} durable memory candidate(s).")

    result = write_okf_bundle(
        memories,
        args.output,
        bundle_title=args.title,
    )
    print(f"OKF bundle written to {result['output_path']}")
    print(f"Total memories: {result['total_memories']}")
    print(f"Per-type: {result['per_type_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

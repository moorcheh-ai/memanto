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
import os
import sys
from pathlib import Path

from claude_code_adapter.extractor import extract_memories
from claude_code_adapter.okf_writer import write_okf_bundle
from claude_code_adapter.parser import (
    iter_project_archives,
    parse_claude_jsonl,
)


def _collect_archives(args: argparse.Namespace) -> list[Path]:
    """Return the deduplicated, ordered list of archive paths from CLI args.

    ``--archive`` and ``--projects`` may overlap (e.g. the same session inside
    a scanned projects directory); each file is parsed exactly once so source
    counts and memory resources stay accurate.
    """
    paths: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        """Append a path unless its normalized form was already seen."""
        key = os.path.normcase(str(path.absolute()))
        if key not in seen:
            seen.add(key)
            paths.append(path)

    if args.archive:
        _add(Path(args.archive))
    if args.projects:
        for archive in iter_project_archives(args.projects):
            _add(archive)
    return paths


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, migrate archive(s) to OKF, and print the summary."""
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

    archives = _collect_archives(args)
    if not archives:
        print(
            "No conversation archives found. Check --archive / --projects paths.",
            file=sys.stderr,
        )
        sys.exit(1)

    memories = []
    total_turns = 0
    for archive in archives:
        turns = parse_claude_jsonl(archive)
        total_turns += len(turns)
        # Extract per archive so each memory's resource references the exact
        # archive it came from instead of a joined list of sources.
        memories.extend(
            extract_memories(
                turns,
                source_path=str(archive),
                include_assistant=not args.user_only,
            )
        )

    if total_turns == 0:
        print(
            "No conversation turns found in the given archive(s).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Parsed {total_turns} conversation turns from {len(archives)} archive(s).")
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

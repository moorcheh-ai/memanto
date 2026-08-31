#!/usr/bin/env python3
"""Generate the migration summary + OKF import dry-run report.

The bounty's "savings report" for provider migrations reports token/latency
savings. The OKF path (Path B) has no such savings figures — `memanto migrate
okf` is a local, lossless import with no API key. Honest substitute this step
produces:

  1. The migration summary: source records -> mapped memories -> per-type
     breakdown (the "Migration Summary" the bounty requires).
  2. The `memanto migrate okf --dry-run` mapping preview from the shipped CLI.

Usage:
    python3 generate_report.py --source claude --input ./conversations.json \
        --output ./okf_output
    python3 generate_report.py --source claude --input ./conversations.json \
        --output ./okf_output --report ./REPORT.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapters  # noqa: F401
from core.adapters import ADAPTERS
from core.models import MemoryEntity
from core.okf_generator import OKFGenerator

_BOX = str.maketrans(dict.fromkeys(
    "─│┌┐└┘├┤┬┴┼╭╮╰╯╱╲╳║═╔╗╚╝╠╣╦╩╬�│。",
))

_HOME = Path.home()
# Redact the user's home directory so reports never leak a personal identifier.
# Match the home prefix only when a true non-word boundary follows (path
# separator, quote, punctuation, whitespace) or end-of-string. \W (not \w)
# is used so_, Unicode letters and other valid filename characters are NOT
# treated as delimiters: a sibling path like <home>_backup stays untouched.
_HOME_RE = re.compile(
    rf"(?<![\w]){re.escape(str(_HOME))}(?=\W|$)",
)


def _redact_home(text: str) -> str:
    return _HOME_RE.sub("~", text)


def _strip_output(text: str) -> str:
    """Strip box-drawing decoration, stray control bytes and personal paths."""
    lines = []
    for line in text.splitlines():
        line = _redact_home(line).translate(_BOX).strip()
        if not line:
            continue
        lines.append(line.rstrip())
    return "\n".join(lines)


def build_report(
    *,
    source: str,
    input_path: str,
    output_dir: str,
    entities: list[MemoryEntity],
    conv_count: int,
    export_dir: str | None = None,
    agent: str | None = None,
) -> str:
    """Build the migration summary + dry-run/export report markdown."""
    lines = ["# Migration Summary", ""]
    lines.append(f"- **Source:** {source}")
    lines.append(f"- **Input:** {input_path}")
    lines.append(f"- **Conversations:** {conv_count}")
    lines.append(f"- **Memory entities mapped:** {len(entities)}")
    lines.append("")
    lines.append("## Per-type breakdown")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|------|-------|")
    counts: dict[str, int] = {}
    for e in entities:
        counts[e.source_type.value] = counts.get(e.source_type.value, 0) + 1
    for t, c in sorted(counts.items()):
        lines.append(f"| {t} | {c} |")
    lines.append("")

    migrate_cmd = [
        sys.executable,
        "-m",
        "memanto",
        "migrate",
        "okf",
        output_dir,
        "--dry-run",
    ]
    if agent:
        migrate_cmd += ["--agent", agent]
    dry = subprocess.run(migrate_cmd, capture_output=True, text=True, check=False)
    lines.append("## Portable export (out leg)")
    lines.append("")
    if export_dir:
        exp = subprocess.run(
            [
                sys.executable,
                "-m",
                "memanto",
                "memory",
                "export",
                "--okf",
                "-o",
                export_dir,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        lines.append(f"- **Export dir:** `{export_dir}`")
        lines.append("")
        lines.append("```")
        lines.append(_strip_output(exp.stdout + exp.stderr))
        lines.append("```")
    else:
        lines.append(
            "_Pass `--export-memanto <dir>` to run `memanto memory export --okf` and prove the portable out-leg._"
        )
    lines.append("")
    both = "\n".join(lines)
    return (
        both
        + "## `memanto migrate okf --dry-run` output\n\n```\n"
        + _strip_output(dry.stdout + dry.stderr)
        + "\n```\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration summary + dry-run report")
    parser.add_argument("--source", choices=list(ADAPTERS.keys()), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="./okf_output/report")
    parser.add_argument("--report", default=None, help="Write report markdown file")
    parser.add_argument(
        "--export-memanto",
        default=None,
        help="Also export the imported memories back to OKF (run 'memanto memory export --okf'); must be inside the agent data dir",
    )
    args = parser.parse_args()

    adapter = ADAPTERS[args.source]()
    raw = adapter.load(args.input)
    conv_list = adapter.get_conversation_list(raw)
    entities = adapter.extract(raw)

    mem_path = OKFGenerator(args.output).generate_bundle(entities)

    report_text = build_report(
        source=args.source,
        input_path=args.input,
        output_dir=args.output,
        entities=entities,
        conv_count=len(conv_list),
        export_dir=args.export_memanto,
    )

    if args.report:
        Path(args.report).write_text(report_text, encoding="utf-8")
        print(f"Report written to {args.report}\n")
    else:
        print(report_text)

    print(f"OKF bundle created at: {mem_path}")


if __name__ == "__main__":
    main()

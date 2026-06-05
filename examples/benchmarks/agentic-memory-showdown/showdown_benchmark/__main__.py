"""Command line entry point for the agentic memory showdown benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from .runner import run_benchmark


def main() -> int:
    """Run the benchmark and write either markdown or JSON output."""
    parser = argparse.ArgumentParser(
        description="Run the Memanto agentic memory showdown benchmark."
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format to emit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write. Defaults to stdout.",
    )
    args = parser.parse_args()

    result = run_benchmark()
    text = result.to_json() if args.format == "json" else result.to_markdown()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

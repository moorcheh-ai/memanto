"""Command-line interface for the LangGraph checkpoint adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapter import convert_checkpoint_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert LangGraph SQLite checkpoints into a portable OKF bundle."
    )
    parser.add_argument("source", type=Path, help="LangGraph SQLite checkpoint file")
    parser.add_argument("output", type=Path, help="Output OKF bundle directory")
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing output bundle"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = convert_checkpoint_database(
        args.source, args.output, overwrite=args.force
    )
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Command-line entry point for the Codex session to OKF adapter."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from codex_session_okf import convert_session


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert privacy-filtered Codex JSONL messages to OKF."
    )
    parser.add_argument("source", type=Path, help="Codex rollout JSONL file")
    parser.add_argument("output", type=Path, help="Destination OKF directory")
    parser.add_argument(
        "--include",
        help="Only export messages matching this case-insensitive regex",
    )
    parser.add_argument("--limit", type=int, help="Maximum messages to export")
    args = parser.parse_args()

    result = convert_session(
        args.source,
        args.output,
        include_pattern=args.include,
        limit=args.limit,
    )
    payload = asdict(result)
    payload["output_dir"] = str(payload["output_dir"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

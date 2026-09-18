#!/usr/bin/env python3
"""Convert ChatGPT or Claude conversation exports into a portable OKF bundle.

Usage:
    python convert.py chatgpt <export-dir> [--out okf_bundle]
    python convert.py claude  <export-dir> [--out okf_bundle]

Then validate against the real Memanto CLI:
    memanto migrate okf ./okf_bundle --dry-run
    memanto migrate okf ./okf_bundle --agent my-agent
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from adapters.chatgpt import load_chatgpt
from adapters.claude import load_claude
from adapters.extract import extract_memories
from adapters.okf import write_bundle

SOURCES = {"chatgpt": load_chatgpt, "claude": load_claude}


def _non_negative_int(v: str) -> int:
    n = int(v)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("export_dir", type=str, help="path to the unzipped export")
    ap.add_argument("--out", default="okf_bundle", help="output bundle directory")
    ap.add_argument("--max-per-type", type=_non_negative_int, default=40)
    ap.add_argument("--max-total", type=_non_negative_int, default=250)
    args = ap.parse_args()
    if args.max_per_type < 0 or args.max_total < 0:
        ap.error("--max-per-type and --max-total must be >= 0")

    loader = SOURCES[args.source]
    conversations = loader(args.export_dir)
    print(f"[1/3] Parsed {len(conversations)} conversations from {args.source} export",
          file=sys.stderr)

    result = extract_memories(conversations, source=args.source,
                              max_per_type=args.max_per_type, max_total=args.max_total)
    stats = result["stats"]
    print(f"[2/3] Extracted {stats['total']} memories "
          f"({len(stats['by_type'])} types) from {stats['turns']} turns", file=sys.stderr)

    written = write_bundle(result["memories"], result["sessions"], stats, args.out)
    print(f"[3/3] Wrote OKF bundle -> {written['bundle_dir']}", file=sys.stderr)
    print()
    print("Next steps:")
    print(f"  memanto migrate okf {shlex.quote(args.out)} --dry-run")
    print(f"  memanto migrate okf {shlex.quote(args.out)} --agent my-agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

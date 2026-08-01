#!/usr/bin/env python3
"""One-command conversion plus validation for the migration showcase."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import chatgpt_to_okf
import validate_okf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="artifact directory; the OKF bundle will be written under it")
    parser.add_argument("--no-redact", action="store_true")
    parser.add_argument("--memanto-dry-run", action="store_true", help="also call `memanto migrate okf ... --dry-run`")
    args = parser.parse_args()
    bundle = args.out / "okf"
    conversations = chatgpt_to_okf.load_conversations(args.export)
    memories = chatgpt_to_okf.make_memories(conversations, redact_output=not args.no_redact)
    manifest = chatgpt_to_okf.write_bundle(memories, bundle, redacted=not args.no_redact)
    original_argv = sys.argv
    try:
        sys.argv = ["validate_okf.py", str(bundle)]
        validation_exit = validate_okf.main()
    finally:
        sys.argv = original_argv
    report = {
        "source": str(chatgpt_to_okf.resolve_export_path(args.export)),
        "okf_bundle": str(bundle),
        "memory_count": manifest["memory_count"],
        "redacted": manifest["redacted"],
        "validation_exit": validation_exit,
        "memanto_dry_run": None,
    }
    if validation_exit:
        return validation_exit
    if args.memanto_dry_run:
        result = subprocess.run(["memanto", "migrate", "okf", str(bundle), "--dry-run"], text=True, capture_output=True)
        report["memanto_dry_run"] = {
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

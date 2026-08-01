#!/usr/bin/env python3
"""Run the Codex rollout -> OKF -> Memanto dry-run proof in one command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from codex_to_okf import export_bundle, validate_bundle


def _normalize_debug_env() -> None:
    # Some shells use DEBUG=release as a generic build marker, while Memanto
    # expects DEBUG to be boolean. Isolate the demo from that ambient convention.
    if os.environ.get("DEBUG", "").lower() not in {
        "",
        "0",
        "1",
        "false",
        "no",
        "off",
        "on",
        "true",
        "yes",
    }:
        os.environ["DEBUG"] = "false"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="real Codex rollout JSONL")
    parser.add_argument("--output", type=Path, default=Path("codex-okf-demo"))
    parser.add_argument("--include", help="case-insensitive selection regex")
    parser.add_argument("--exclude", help="case-insensitive exclusion regex")
    parser.add_argument("--max-records", type=int, default=25)
    parser.add_argument("--take", choices=("first", "last"), default="last")
    parser.add_argument(
        "--golden", type=Path, help="golden Q&A JSON tied to the selected source"
    )
    parser.add_argument(
        "--redact-literal",
        action="append",
        default=[],
        help="private literal to redact; repeatable and never persisted",
    )
    return parser


def main() -> int:
    _normalize_debug_env()
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    args = build_parser().parse_args()
    export_args = argparse.Namespace(
        source=args.source,
        output=args.output,
        roles=["user", "assistant"],
        include=args.include,
        exclude=args.exclude,
        max_records=args.max_records,
        take=args.take,
        redact_literal=args.redact_literal,
        force=True,
    )
    manifest = export_bundle(export_args)
    report_path = args.output / "roundtrip_report.json"
    validation = validate_bundle(
        argparse.Namespace(
            source=args.source,
            bundle=args.output,
            report=report_path,
            golden=args.golden,
        )
    )

    # Exercise the same pure loader/mapper used by `memanto migrate okf
    # --dry-run` without requiring a configured agent or Moorcheh API key.
    loaded = load_okf_bundle(args.output)
    mapped = map_okf(loaded)
    dry_run = {
        "okf_nodes": len(loaded["memories"]),
        "mapped_memories": len(mapped),
        "skipped": len(loaded["memories"]) - len(mapped),
        "writes_performed": 0,
    }
    (args.output / "memanto_dry_run_report.json").write_text(
        json.dumps(dry_run, indent=2) + "\n", encoding="utf-8"
    )
    result = {
        "valid": validation["valid"] and dry_run["skipped"] == 0,
        "selected": manifest["selection"]["selected"],
        "source_to_okf_coverage": validation["source_to_okf_coverage"],
        "content_hash_parity": validation["content_hash_parity"],
        "privacy_gate_findings": validation["privacy_gate_findings"],
        "golden_qa": validation["golden_qa"],
        "memanto_dry_run": dry_run,
        "output": str(args.output.resolve()),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproduce the committed migration and bundle checks without cloud calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="new directory for the run artifacts")
    args = parser.parse_args()
    example = Path(__file__).resolve().parent
    root = example.parents[2]
    if args.out:
        output = args.out.resolve()
        output.mkdir(parents=True, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix="goose-okf-review-"))

    def run(name: str, *arguments: str | Path) -> None:
        result = subprocess.run(
            [sys.executable, *map(str, arguments)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        log = output / f"{name}.txt"
        log.write_text(result.stdout, encoding="utf-8")
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'} ({log})")
        if result.returncode:
            raise SystemExit(result.returncode)

    bundle = output / "goose-okf"
    run(
        "01-convert",
        example / "goose_sessions_to_okf.py",
        example / "fixtures/goose-session-export.json",
        "--out",
        bundle,
        "--summary",
        output / "migration-summary.json",
    )
    run(
        "02-validate-generated",
        example / "validate_roundtrip.py",
        bundle,
        "--report",
        output / "generated-bundle-checks.md",
    )
    run(
        "03-cli-dry-run",
        "-m",
        "memanto.cli.main",
        "migrate",
        "okf",
        bundle,
        "--dry-run",
    )
    run(
        "04-validate-recorded-export",
        example / "validate_roundtrip.py",
        example / "sample_output/memanto-exported-okf",
        "--report",
        output / "recorded-export-checks.md",
    )
    summary = json.loads(
        (output / "migration-summary.json").read_text(encoding="utf-8")
    )
    print(
        f"\n{summary['source_sessions']} session(s), "
        f"{summary['source_messages']} messages, {summary['mapped_memories']} memories."
    )
    print("Local checks complete. No new Goose run or cloud import was performed.")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()

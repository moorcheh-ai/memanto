#!/usr/bin/env python3
"""Run the offline Antigravity → OKF → Memanto fidelity showcase."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from migrate_antigravity import migrate
from validate_round_trip import validate

ROOT = Path(__file__).resolve().parent


def run_memanto_dry_run(bundle: Path) -> dict[str, object]:
    """Exercise the repository's shipped OKF CLI without cloud writes."""
    command = [
        sys.executable,
        "-m",
        "memanto.cli.main",
        "migrate",
        "okf",
        str(bundle),
        "--dry-run",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or completed.stdout).splitlines()[-8:])
        raise RuntimeError(
            f"Memanto CLI dry-run failed with exit code {completed.returncode}:\n{tail}"
        )
    return {
        "command": "memanto migrate okf sample/okf --dry-run",
        "exit_code": completed.returncode,
        "writes_performed": False,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "sample" / "source")
    parser.add_argument("--output", type=Path, default=ROOT / "sample" / "okf")
    parser.add_argument(
        "--skip-cli-preview",
        action="store_true",
        help="Skip the shipped memanto migrate okf --dry-run call",
    )
    args = parser.parse_args()

    migration = migrate(args.source, args.output, force=True)
    validation = validate(args.source, args.output, ROOT / "sample" / "golden_qa.json")
    cli = None if args.skip_cli_preview else run_memanto_dry_run(args.output)
    metrics = args.output / "metrics"
    _write_json(metrics / "round-trip-validation.json", validation)
    if cli is not None:
        _write_json(metrics / "memanto-cli-dry-run.json", cli)
    report = {"migration": migration, "validation": validation, "memanto_cli": cli}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

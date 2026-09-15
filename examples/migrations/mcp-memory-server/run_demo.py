#!/usr/bin/env python3
"""Run the complete reproducible MCP Memory → Memanto OKF showcase."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from generate_real_source import populate
from migrate_mcp_memory import migrate
from validate_round_trip import validate

ROOT = Path(__file__).resolve().parent


def run_memanto_dry_run(okf_path: Path) -> dict[str, object]:
    """Feed the generated bundle through the shipped Memanto CLI."""
    executable = Path(sys.executable).with_name("memanto")
    if not executable.is_file():
        discovered = shutil.which("memanto")
        if discovered is None:
            raise RuntimeError(
                "memanto CLI was not found; install the repository before running "
                "the complete showcase"
            )
        executable = Path(discovered)

    command = [str(executable), "migrate", "okf", str(okf_path), "--dry-run"]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Memanto CLI dry-run failed with exit code {completed.returncode}"
        )
    return {
        "command": "memanto migrate okf sample/okf --dry-run",
        "exit_code": completed.returncode,
        "writes_performed": False,
    }


def main() -> int:
    """Run source generation, migration, validation, and CLI preview."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate source via the official npm MCP server before migration",
    )
    parser.add_argument(
        "--source",
        default=str(ROOT / "sample" / "source" / "memory.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "sample" / "okf"),
    )
    parser.add_argument(
        "--skip-cli-preview",
        action="store_true",
        help="Skip the shipped `memanto migrate okf --dry-run` verification",
    )
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if args.regenerate:
        populate(source, force=True)

    migration = migrate(source, output, force=True)
    validation = validate(
        source,
        output,
        ROOT / "sample" / "golden_qa.json",
    )
    cli_preview = None
    if not args.skip_cli_preview:
        cli_preview = run_memanto_dry_run(output)
    report = {
        "migration": migration,
        "validation": validation,
        "memanto_cli_dry_run": cli_preview,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (output / "metrics" / "round-trip-validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if cli_preview is not None:
        (output / "metrics" / "memanto-cli-dry-run.json").write_text(
            json.dumps(cli_preview, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        (output / "metrics" / "memanto-cli-dry-run.json").unlink(missing_ok=True)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

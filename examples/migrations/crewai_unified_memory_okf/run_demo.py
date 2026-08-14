#!/usr/bin/env python3
"""Run the complete CrewAI -> OKF -> Memanto dry-run showcase."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from generate_source import generate
from migrate import read_lancedb_records, write_okf_bundle
from validate import validate

DRY_RUN_TIMEOUT_SECONDS = 120


def _configure_utf8_console() -> None:
    """Avoid Windows legacy-codepage failures in CrewAI/Memanto rich output."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _sanitize_transcript(text: str, *, bundle: Path) -> str:
    """Replace machine-specific absolute paths with stable placeholders."""

    replacements = (
        (str(bundle.resolve()), "<OKF_BUNDLE>"),
        (bundle.resolve().as_posix(), "<OKF_BUNDLE>"),
        (str(Path.home().resolve()), "<USER_HOME>"),
        (Path.home().resolve().as_posix(), "<USER_HOME>"),
    )
    sanitized = text
    for value, placeholder in replacements:
        sanitized = sanitized.replace(value, placeholder)
    return sanitized


def run_demo(output: Path, *, skip_memanto_cli: bool = False) -> int:
    """Run source generation, OKF migration, dry-run import, and validation."""

    output = output.resolve()
    source_database = output / "source" / "crewai-memory"
    evidence_dir = output / "evidence"
    okf_bundle = output / "okf-bundle"

    print("\n[1/4] Running CrewAI's public unified-memory API")
    generate(source_database, evidence_dir, force=True)

    print("\n[2/4] Converting the real LanceDB store to OKF")
    records = read_lancedb_records(source_database)
    write_okf_bundle(
        records,
        okf_bundle,
        source_database=source_database,
        force=True,
    )

    print("\n[3/4] Running Memanto's shipped OKF dry-run")
    if skip_memanto_cli:
        print("Skipped by --skip-memanto-cli")
    else:
        environment = os.environ.copy()
        environment["NO_COLOR"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        environment["COLUMNS"] = "240"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memanto",
                    "migrate",
                    "okf",
                    str(okf_bundle),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=DRY_RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Memanto dry-run did not finish within "
                f"{DRY_RUN_TIMEOUT_SECONDS} seconds"
            ) from exc
        transcript = result.stdout + (
            "\nSTDERR:\n" + result.stderr if result.stderr else ""
        )
        transcript = _sanitize_transcript(transcript, bundle=okf_bundle)
        (evidence_dir / "memanto-dry-run.txt").write_text(
            transcript, encoding="utf-8", newline="\n"
        )
        print(transcript.rstrip())
        if result.returncode:
            raise RuntimeError(
                f"Memanto dry-run failed with exit code {result.returncode}"
            )

    print("\n[4/4] Verifying exact hashes, mappings, and golden recall")
    report = validate(
        source_database,
        okf_bundle,
        evidence_dir / "source-run.json",
        evidence_dir,
    )
    if not report["passed"]:
        raise RuntimeError("Round-trip validation failed")

    print("\nFreedom loop complete: CrewAI -> owned OKF -> Memanto-ready")
    print(f"Artifacts: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the end-to-end demo command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "artifacts" / "latest",
        help="Generated run directory",
    )
    parser.add_argument(
        "--skip-memanto-cli",
        action="store_true",
        help="Skip only the shipped CLI dry-run (useful for adapter-only debugging)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Configure the console and run the demo from CLI arguments."""

    _configure_utf8_console()
    args = build_parser().parse_args(argv)
    return run_demo(args.output, skip_memanto_cli=args.skip_memanto_cli)


if __name__ == "__main__":
    raise SystemExit(main())

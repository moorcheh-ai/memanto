#!/usr/bin/env python3
"""Run the real OKF → Memanto → OKF round trip against Moorcheh Cloud."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from examples.migrations.hindsight import (
        adapter,
        validate_memanto,
        verify_artifacts,
    )
except ModuleNotFoundError:
    import adapter  # type: ignore[no-redef]
    import validate_memanto  # type: ignore[no-redef]
    import verify_artifacts  # type: ignore[no-redef]

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[2]
DEFAULT_ARTIFACTS = EXAMPLE_DIR / "artifacts" / "beacon-live-run"
DEFAULT_BUNDLE = DEFAULT_ARTIFACTS / "hindsight-okf"
DEFAULT_OUTPUT = EXAMPLE_DIR / "artifacts" / "local-roundtrip-run"


def normalize_transcript(value: str) -> str:
    """Remove developer-specific absolute paths from captured CLI evidence."""
    normalized = value.replace(str(REPO_ROOT), "<repo>")
    normalized = normalized.replace(str(Path.home() / ".memanto"), "~/.memanto")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    return (
        "# Captured from a real command; local absolute paths are normalized.\n"
        f"{normalized.rstrip()}\n"
    )


def run_command(command: list[str], artifact_path: Path) -> None:
    """Run one CLI command and persist its sanitized terminal transcript."""
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    transcript = f"$ {' '.join(command)}\n\n{result.stdout}"
    if result.stderr:
        transcript += f"\n[stderr]\n{result.stderr}"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        normalize_transcript(transcript),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise adapter.AdapterError(
            f"Command failed with exit code {result.returncode}; see {artifact_path}"
        )


def copy_staged_export(staged_export: Path, artifact_export: Path) -> None:
    """Copy a CLI export from Memanto's safe data directory into evidence."""
    if not staged_export.is_dir() or not any(staged_export.iterdir()):
        raise adapter.AdapterError(
            f"Memanto staged export is missing or empty: {staged_export}"
        )
    shutil.copytree(staged_export, artifact_export, dirs_exist_ok=True)


def ensure_fresh_agent(client: Any, agent_id: str) -> None:
    """Create and activate a new isolated agent without touching existing data."""
    existing_ids = {str(item.get("agent_id")) for item in client.list_agents()}
    if agent_id in existing_ids:
        raise adapter.AdapterError(
            f"Memanto agent {agent_id!r} already exists; choose a fresh --agent ID"
        )
    client.create_agent(
        agent_id,
        pattern="project",
        description="Hindsight to OKF migration round-trip verification",
    )
    client.activate_agent(agent_id)


def build_parser() -> argparse.ArgumentParser:
    """Create the cloud round-trip argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh Memanto agent, import the Hindsight OKF bundle, "
            "validate recall parity, and export the agent back to OKF."
        )
    )
    parser.add_argument(
        "--agent",
        required=True,
        help="Fresh isolated Memanto agent ID to create.",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_BUNDLE,
        help=f"Input OKF bundle (default: {DEFAULT_BUNDLE}).",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=DEFAULT_ARTIFACTS,
        help=f"Source evidence directory (default: {DEFAULT_ARTIFACTS}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Round-trip evidence root; the OKF re-export is written below it "
            f"(default: {DEFAULT_OUTPUT})."
        ),
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Execute the real cloud round trip and return a process status."""
    args = build_parser().parse_args(argv)
    bundle = args.bundle.expanduser().resolve()
    source_artifacts = args.artifacts.expanduser().resolve()
    output = args.output.expanduser().resolve()
    export_output = output / "memanto-export"
    evidence_dir = output / "evidence"
    staged_export = Path.home() / ".memanto" / "exports" / f"{args.agent}_roundtrip_okf"
    executable = REPO_ROOT / ".venv" / "bin" / "memanto"

    try:
        if not bundle.is_dir():
            raise adapter.AdapterError(f"Input OKF bundle does not exist: {bundle}")
        if not executable.exists():
            raise adapter.AdapterError(
                f"Memanto development environment not found at {executable}"
            )
        if output.exists() and not output.is_dir():
            raise adapter.AdapterError(
                f"Round-trip output exists and is not a directory: {output}"
            )
        if export_output.exists() and any(export_output.iterdir()):
            raise adapter.AdapterError(f"Export output is not empty: {export_output}")
        if staged_export.exists() and any(staged_export.iterdir()):
            raise adapter.AdapterError(
                f"Staged export output is not empty: {staged_export}"
            )

        preflight = verify_artifacts.verify(source_artifacts)
        expected_count = int(preflight["importable_records"])

        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        api_key = ConfigManager().get_api_key()
        if not api_key:
            raise adapter.AdapterError(
                "MOORCHEH_API_KEY is not configured in ~/.memanto/.env"
            )
        client = SdkClient(api_key)
        print(f"[1/4] Creating fresh Memanto agent {args.agent}", flush=True)
        ensure_fresh_agent(client, args.agent)

        print(f"[2/4] Importing {expected_count} OKF concepts", flush=True)
        run_command(
            [
                str(executable),
                "migrate",
                "okf",
                str(bundle),
                "--agent",
                args.agent,
            ],
            evidence_dir / "memanto-import.txt",
        )

        print("[3/4] Validating shared-set recall parity", flush=True)
        validation_status = validate_memanto.run(
            [
                "--agent",
                args.agent,
                "--artifacts",
                str(source_artifacts),
                "--evidence-output",
                str(evidence_dir),
                "--expected-count",
                str(expected_count),
            ]
        )
        if validation_status != 0:
            raise adapter.AdapterError(
                "Memanto destination recall did not fully pass; "
                "see evidence/memanto-recall.json"
            )

        print("[4/4] Exporting Memanto back to portable OKF", flush=True)
        run_command(
            [
                str(executable),
                "memory",
                "export",
                "--okf",
                "--split",
                "type",
                "--limit",
                "100",
                "--agent",
                args.agent,
                "--output",
                str(staged_export),
            ],
            evidence_dir / "memanto-export.txt",
        )
        copy_staged_export(staged_export, export_output)

        from memanto.cli.migrate.okf_loader import load_okf_bundle

        exported_count = len(load_okf_bundle(export_output)["memories"])
        if exported_count != expected_count:
            raise adapter.AdapterError(
                f"Memanto re-export contains {exported_count}/{expected_count} "
                "expected concepts"
            )
        roundtrip_summary = {
            "schema": "hindsight-memanto-okf-roundtrip/v1",
            "agent_id": args.agent,
            "input_concepts": expected_count,
            "indexed_memories": expected_count,
            "exported_concepts": exported_count,
            "recall_report": "evidence/memanto-recall.json",
            "parity_report": "evidence/recall-parity.json",
            "export_bundle": "memanto-export",
        }
        output.mkdir(parents=True, exist_ok=True)
        (output / "roundtrip-summary.json").write_text(
            json.dumps(roundtrip_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        adapter.AdapterError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Round trip complete: {expected_count} in, "
        f"{exported_count} recalled and exported.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

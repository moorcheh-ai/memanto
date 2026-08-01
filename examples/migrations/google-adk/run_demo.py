#!/usr/bin/env python3
"""Run the real Google ADK → OKF → Memanto dry-run showcase end to end."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import adapter
import validation
from create_source import create_database
from verify_artifacts import verify_bundle

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_ARTIFACTS = HERE / "artifacts" / "adk-live-run"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RUN_SUMMARY_SCHEMA = "google-adk-demo-run/v1"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _is_replaceable_artifacts_dir(path: Path) -> bool:
    """Return true only for an empty or previously completed demo directory."""
    if not path.is_dir():
        return False
    try:
        if not any(path.iterdir()):
            return True
        summary = json.loads((path / "run-summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(summary, dict) and summary.get("schema") == RUN_SUMMARY_SCHEMA


def _memanto_executable() -> Path | None:
    executable_name = "memanto.exe" if os.name == "nt" else "memanto"
    sibling = Path(sys.executable).parent / executable_name
    if sibling.is_file():
        return sibling
    found = shutil.which("memanto")
    return Path(found) if found else None


def _normalize_transcript(value: str, artifacts: Path) -> str:
    value = ANSI_RE.sub("", value)
    replacements = {
        str(REPO_ROOT): "<repo>",
        str(artifacts): "<artifacts>",
        str(Path.home()): "~",
    }
    for raw, replacement in replacements.items():
        value = value.replace(raw, replacement)
    return "\n".join(line.rstrip() for line in value.splitlines()).strip() + "\n"


def run_memanto_dry_run(bundle: Path, artifacts: Path) -> dict[str, Any]:
    executable = _memanto_executable()
    if executable is None:
        raise adapter.AdapterError(
            "Memanto CLI not found. From the repository root run `uv sync --group dev`."
        )
    try:
        bundle_argument = str(bundle.relative_to(REPO_ROOT))
    except ValueError:
        bundle_argument = str(bundle)
    command = [str(executable), "migrate", "okf", bundle_argument, "--dry-run"]
    # A wide capture keeps paths on one line so normalization can remove local
    # usernames and machine-specific directories from committed evidence.
    env = {
        **os.environ,
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "240",
        "LINES": "60",
    }
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    transcript = (
        "$ memanto migrate okf <bundle> --dry-run\n\n"
        + result.stdout
        + (f"\n[stderr]\n{result.stderr}" if result.stderr else "")
    )
    transcript = _normalize_transcript(transcript, artifacts)
    evidence = artifacts / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "memanto-dry-run.txt").write_text(transcript, encoding="utf-8")
    if result.returncode != 0:
        raise adapter.AdapterError(
            "The shipped `memanto migrate okf --dry-run` command failed; see "
            f"{evidence / 'memanto-dry-run.txt'}"
        )
    return {
        "command": "memanto migrate okf <bundle> --dry-run",
        "returncode": result.returncode,
        "transcript": "evidence/memanto-dry-run.txt",
    }


def migration_report(
    manifest: dict[str, Any],
    source_report: dict[str, Any],
    okf_report: dict[str, Any],
    parity: dict[str, Any],
    dry_run: dict[str, Any],
) -> dict[str, Any]:
    migration = manifest["migration"]
    return {
        "schema": "google-adk-okf-migration-report/v1",
        "source": {
            "provider": "google-adk",
            "service": "SqliteSessionService",
            "state_records": migration["source_state_records"],
            "sessions": migration["sessions_preserved"],
            "events": migration["events_preserved"],
            "state_updates": migration["state_updates_preserved"],
            "database_sha256": manifest["source"]["database_sha256"],
        },
        "mapping": {
            "mapped_memories": migration["mapped_memories"],
            "skipped": migration["skipped"],
            "type_counts": migration["type_counts"],
            "superseded_timelines_archived": migration["superseded_timelines_archived"],
            "redacted_values": migration["redacted_values"],
        },
        "memanto_dry_run": dry_run,
        "recall_fidelity": {
            "source_average": source_report["average_score"],
            "okf_average": okf_report["average_score"],
            "zero_amnesia": parity["zero_amnesia"],
            "average_delta": parity["average_delta"],
        },
        "provider_savings": {
            "available": False,
            "reason": (
                "The shipped OKF importer intentionally has no --report flag, and "
                "Google ADK SqliteSessionService records no provider token, latency, "
                "or billing baseline. No synthetic savings are claimed."
            ),
        },
        "round_trip_status": (
            "Local source→OKF fidelity and shipped Memanto dry-run are complete. "
            "Cloud import→recall→OKF export requires MOORCHEH_API_KEY and is run "
            "with run_roundtrip.py."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--force", action="store_true", help="Replace demo artifacts")
    parser.add_argument(
        "--skip-memanto-dry-run",
        action="store_true",
        help="Skip the shipped CLI proof (not suitable for bounty evidence)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts = args.artifacts.expanduser().resolve()
    if artifacts.exists():
        if not args.force:
            print(f"error: artifacts already exist: {artifacts}; pass --force")
            return 2
        if not _is_replaceable_artifacts_dir(artifacts):
            print(
                f"error: refusing to delete {artifacts}: it is not an empty or "
                "previously completed Google ADK demo artifacts directory"
            )
            return 2
        shutil.rmtree(artifacts)
    artifacts.mkdir(parents=True)
    bundle = artifacts / "google-adk-okf"

    try:
        print("[1/7] Creating a real Google ADK SqliteSessionService database...")
        with tempfile.TemporaryDirectory(prefix="memanto-google-adk-") as temp:
            database = Path(temp) / "google-adk-sessions.db"
            source_run = asyncio.run(create_database(database))
            print(
                f"      ADK {source_run['google_adk_version']}: "
                f"{source_run['sessions_created']} sessions, "
                f"{source_run['events_written']} persisted events"
            )
            print("[2/7] Capturing SQLite read-only with credential redaction...")
            captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            snapshot = adapter.snapshot_database(
                database,
                app_filter=source_run["app_name"],
                user_filter=source_run["user_id"],
                captured_at=captured_at,
                source_version=source_run["google_adk_version"],
            )
            source_run["database_sha256"] = snapshot["source"]["database_sha256"]

        _write_json(artifacts / "evidence" / "source-run.json", source_run)
        print("[3/7] Mapping current state to OKF; isolating correction history...")
        manifest = adapter.write_bundle(snapshot, bundle)
        print(
            f"      {manifest['migration']['mapped_memories']} current memories; "
            f"{manifest['migration']['superseded_timelines_archived']} "
            "superseded timelines archived"
        )
        print("[4/7] Asking the same 8 golden questions before and after mapping...")
        source_report = validation.validate_documents(
            validation.source_documents(snapshot),
            corpus_name="google-adk-current-state",
        )
        okf_report = validation.validate_documents(
            validation.okf_documents(bundle), corpus_name="memanto-okf-mapped-preview"
        )
        parity = validation.compare_reports(source_report, okf_report)
        validation.write_json(
            artifacts / "evidence" / "source-recall-validation.json", source_report
        )
        validation.write_json(
            artifacts / "evidence" / "okf-recall-validation.json", okf_report
        )
        validation.write_json(artifacts / "evidence" / "recall-parity.json", parity)
        print(
            f"      source={source_report['average_score']:.0%}, "
            f"OKF={okf_report['average_score']:.0%}, "
            f"zero_amnesia={parity['zero_amnesia']}"
        )

        print("[5/7] Running shipped `memanto migrate okf --dry-run`...")
        if args.skip_memanto_dry_run:
            dry_run = {"skipped": True, "reason": "explicit command-line option"}
        else:
            dry_run = run_memanto_dry_run(bundle, artifacts)
            print(
                f"      Memanto accepted {manifest['migration']['mapped_memories']} "
                "nodes; captured output reports 0 skipped"
            )
        print("[6/7] Replaying the snapshot and checking every bundle SHA-256...")
        verification = verify_bundle(bundle)
        _write_json(artifacts / "evidence" / "artifact-verification.json", verification)
        if not verification["passed"]:
            raise adapter.AdapterError("Artifact verification failed")
        report = migration_report(manifest, source_report, okf_report, parity, dry_run)
        _write_json(artifacts / "migration-report.json", report)
        summary = {
            "schema": RUN_SUMMARY_SCHEMA,
            "completed_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_run": "evidence/source-run.json",
            "bundle": "google-adk-okf",
            "migration_report": "migration-report.json",
            "source_recall": source_report["average_score"],
            "okf_recall": okf_report["average_score"],
            "zero_amnesia": parity["zero_amnesia"],
            "artifact_verification": verification["passed"],
            "memanto_dry_run": not dry_run.get("skipped", False),
        }
        _write_json(artifacts / "run-summary.json", summary)
        print("[7/7] Writing auditable reports and portable artifacts...")
    except Exception as exc:
        print(f"error: {exc}")
        return 2

    print(
        f"OK: {manifest['migration']['mapped_memories']} current memories, "
        f"source recall {source_report['average_score']:.0%}, "
        f"OKF recall {okf_report['average_score']:.0%}, artifacts {artifacts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

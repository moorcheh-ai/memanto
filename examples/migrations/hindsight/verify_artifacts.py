#!/usr/bin/env python3
"""Verify that committed Hindsight migration evidence is internally consistent."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from examples.migrations.hindsight import adapter
    from examples.migrations.hindsight.validation import rescore_report
except ModuleNotFoundError:
    import adapter  # type: ignore[no-redef]
    from validation import rescore_report

EXAMPLE_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACTS = EXAMPLE_DIR / "artifacts" / "beacon-live-run"


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object or raise a concise verification failure."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise adapter.AdapterError(
            f"Could not read JSON evidence {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise adapter.AdapterError(f"Expected a JSON object in {path}")
    return value


def file_tree(root: Path) -> dict[Path, bytes]:
    """Return a byte-exact relative file tree."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def require_equal(actual: Any, expected: Any, label: str) -> None:
    """Raise a readable failure when committed evidence disagrees."""
    if actual != expected:
        raise adapter.AdapterError(
            f"{label} mismatch: expected {expected!r}, found {actual!r}"
        )


def verify_roundtrip(artifacts: Path, expected_count: int) -> dict[str, Any]:
    """Verify live Memanto recall and re-export evidence when present."""
    summary = read_json(artifacts / "roundtrip-summary.json")
    parity = read_json(artifacts / "evidence" / "recall-parity.json")
    destination = read_json(artifacts / "evidence" / "memanto-recall.json")
    export = artifacts / "memanto-export"

    from memanto.cli.migrate.okf_loader import load_okf_bundle

    exported_count = len(load_okf_bundle(export)["memories"])
    for key in ("input_concepts", "indexed_memories", "exported_concepts"):
        require_equal(summary[key], expected_count, f"roundtrip {key}")
    require_equal(exported_count, expected_count, "re-export concept count")
    require_equal(
        destination["passed"],
        destination["questions"],
        "destination full-pass count",
    )
    require_equal(
        parity["retained_or_improved"],
        parity["questions"],
        "recall parity retained cases",
    )
    require_equal(parity["mean_score_retention"], 1.0, "mean score retention")
    return {
        "agent_id": summary["agent_id"],
        "destination_passed": destination["passed"],
        "exported_concepts": exported_count,
    }


def verify(
    artifacts: Path,
    *,
    roundtrip_artifacts: Path | None = None,
    require_roundtrip_evidence: bool = False,
) -> dict[str, Any]:
    """Verify source, bundle, dry-run, and optional cloud round-trip evidence."""
    artifacts = artifacts.expanduser().resolve()
    bundle = artifacts / "hindsight-okf"
    source_path = bundle / "source" / "hindsight-memory-snapshot.json"
    manifest = read_json(bundle / "migration-manifest.json")
    run_summary = read_json(artifacts / "run-summary.json")
    migration_report = read_json(artifacts / "evidence" / "migration-report.json")
    source_report = rescore_report(
        read_json(artifacts / "evidence" / "source-recall.json")
    )
    snapshot = adapter.load_snapshot(source_path)

    with tempfile.TemporaryDirectory(prefix="hindsight-okf-verify-") as temp:
        replay = Path(temp) / "hindsight-okf"
        replay_manifest = adapter.build_bundle(snapshot, replay)
        bundle_tree = file_tree(bundle)
        replay_tree = file_tree(replay)
        if bundle_tree != replay_tree:
            differing = sorted(
                (
                    path
                    for path in bundle_tree.keys() | replay_tree.keys()
                    if bundle_tree.get(path) != replay_tree.get(path)
                ),
                key=str,
            )
            detail = f"; differing paths: {differing[:3]}" if differing else ""
            raise adapter.AdapterError(
                f"Committed OKF bundle is not byte-identical to replay{detail}"
            )

    snapshot_sha = replay_manifest["source"]["snapshot_sha256"]
    require_equal(
        manifest["source"]["snapshot_sha256"],
        snapshot_sha,
        "manifest snapshot SHA-256",
    )
    require_equal(
        run_summary["snapshot_sha256"],
        snapshot_sha,
        "run-summary snapshot SHA-256",
    )

    migration = manifest["migration"]
    expected_count = int(migration["importable_records"])
    require_equal(
        run_summary["migration"],
        migration,
        "run-summary migration",
    )
    require_equal(
        migration_report["dry_run"]["mapped_memories"],
        expected_count,
        "dry-run mapped count",
    )
    require_equal(
        source_report["passed"],
        source_report["questions"],
        "source full-pass count",
    )

    bundle_files = [path for path in bundle.rglob("*") if path.is_file()]
    require_equal(
        migration_report["okf_input_bundle"]["files"],
        len(bundle_files),
        "OKF file count",
    )
    require_equal(
        migration_report["okf_input_bundle"]["bytes"],
        sum(path.stat().st_size for path in bundle_files),
        "OKF byte count",
    )
    require_equal(
        migration_report["source"]["snapshot_bytes"],
        source_path.stat().st_size,
        "source snapshot byte count",
    )

    result: dict[str, Any] = {
        "source_records": migration["source_records"],
        "importable_records": expected_count,
        "archived_records": migration["archived_records"],
        "source_passed": source_report["passed"],
        "snapshot_sha256": snapshot_sha,
        "byte_identical_replay": True,
    }
    roundtrip_root = (
        roundtrip_artifacts.expanduser().resolve()
        if roundtrip_artifacts is not None
        else artifacts
    )
    roundtrip_path = roundtrip_root / "roundtrip-summary.json"
    if roundtrip_path.exists():
        result["roundtrip"] = verify_roundtrip(roundtrip_root, expected_count)
    elif require_roundtrip_evidence:
        raise adapter.AdapterError(
            "Live round-trip evidence is required but roundtrip-summary.json is missing"
        )
    else:
        result["roundtrip"] = None
    return result


def build_parser() -> argparse.ArgumentParser:
    """Create the evidence verifier argument parser."""
    parser = argparse.ArgumentParser(
        description="Verify committed Hindsight migration and recall evidence."
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=DEFAULT_ARTIFACTS,
        help=f"Artifact directory (default: {DEFAULT_ARTIFACTS}).",
    )
    parser.add_argument(
        "--require-roundtrip",
        action="store_true",
        help="Fail unless live Memanto recall and re-export evidence exists.",
    )
    parser.add_argument(
        "--roundtrip-artifacts",
        type=Path,
        help=(
            "Separate live round-trip evidence root "
            "(defaults to the source artifact directory)."
        ),
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run evidence verification and print a compact result."""
    args = build_parser().parse_args(argv)
    try:
        result = verify(
            args.artifacts,
            roundtrip_artifacts=args.roundtrip_artifacts,
            require_roundtrip_evidence=args.require_roundtrip,
        )
    except (adapter.AdapterError, KeyError, OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

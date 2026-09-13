#!/usr/bin/env python3
"""Reconstruct canonical PydanticAI history from an adapter-generated bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class ReconstructionError(ValueError):
    """Raised when a bundle cannot be reconstructed without loss or ambiguity."""

    pass


def canonical_json(value: Any) -> bytes:
    """Return the canonical UTF-8 JSON encoding used for integrity hashes."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_non_finite(constant: str) -> None:
    """Reject non-standard non-finite constants during JSON decoding."""
    raise ReconstructionError(f"non-finite JSON number is not supported: {constant}")


def _bundle_path(bundle_root: Path, relative: str) -> Path:
    """Resolve a manifest path while requiring it to remain inside the bundle."""
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ReconstructionError(f"absolute manifest path: {relative}")
    candidate = (bundle_root / relative_path).resolve()
    try:
        candidate.relative_to(bundle_root)
    except ValueError as exc:
        raise ReconstructionError(f"manifest path escapes bundle: {relative}") from exc
    return candidate


def reconstruct(bundle: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify a bundle and reconstruct its canonical PydanticAI messages."""
    bundle_root = bundle.resolve()
    manifest_path = _bundle_path(bundle_root, "migration-manifest.json")
    if not manifest_path.is_file():
        raise ReconstructionError("migration-manifest.json is missing")
    manifest = json.loads(
        manifest_path.read_text("utf-8"), parse_constant=_reject_non_finite
    )
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ReconstructionError("manifest file hashes are missing")

    mismatches: list[str] = []
    validated_paths: dict[str, Path] = {}
    for relative, expected in expected_files.items():
        if not isinstance(relative, str):
            raise ReconstructionError("manifest paths must be strings")
        path = _bundle_path(bundle_root, relative)
        validated_paths[relative] = path
        actual = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
        if actual != expected:
            mismatches.append(relative)
    if mismatches:
        raise ReconstructionError(
            "bundle file hash mismatch: " + ", ".join(sorted(mismatches))
        )

    sidecars = [
        path
        for relative, path in sorted(validated_paths.items())
        if relative.startswith("source/messages/") and relative.endswith(".json")
    ]
    messages = [
        json.loads(path.read_text("utf-8"), parse_constant=_reject_non_finite)
        for path in sidecars
    ]
    canonical_sha = hashlib.sha256(canonical_json(messages)).hexdigest()
    expected_sha = manifest.get("output_canonical_sha256")
    if canonical_sha != expected_sha:
        raise ReconstructionError(
            f"canonical history hash mismatch: {canonical_sha} != {expected_sha}"
        )
    return messages, {
        "messages": len(messages),
        "canonical_sha256": canonical_sha,
        "matches_manifest": True,
        "lossless": bool(manifest.get("lossless")),
    }


def main() -> int:
    """Run bundle reconstruction and optionally write messages and a report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    messages, report = reconstruct(args.bundle)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(messages, allow_nan=False, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

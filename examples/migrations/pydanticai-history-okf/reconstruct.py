#!/usr/bin/env python3
"""Reconstruct canonical PydanticAI history from an adapter-generated bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class ReconstructionError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def reconstruct(bundle: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path = bundle / "migration-manifest.json"
    if not manifest_path.is_file():
        raise ReconstructionError("migration-manifest.json is missing")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ReconstructionError("manifest file hashes are missing")

    mismatches: list[str] = []
    for relative, expected in expected_files.items():
        path = bundle / relative
        actual = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
        if actual != expected:
            mismatches.append(relative)
    if mismatches:
        raise ReconstructionError(
            "bundle file hash mismatch: " + ", ".join(sorted(mismatches))
        )

    sidecars = sorted((bundle / "source" / "messages").glob("*.json"))
    messages = [json.loads(path.read_text("utf-8")) for path in sidecars]
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
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    messages, report = reconstruct(args.bundle)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(messages, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

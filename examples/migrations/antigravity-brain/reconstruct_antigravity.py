#!/usr/bin/env python3
"""Reconstruct Antigravity brain artifacts from an OKF or Memanto export."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import zlib
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from migrate_antigravity import SOURCE_MARKER_RE

RECONSTRUCTION_SENTINEL = ".antigravity-reconstruction-v1"


def _decode_record(encoded: str, source: Path) -> dict[str, Any]:
    try:
        compressed = base64.b64decode(encoded, validate=True)
        value = json.loads(zlib.decompress(compressed).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, zlib.error) as exc:
        raise ValueError(f"Invalid Antigravity source marker in {source}") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError(f"Unsupported Antigravity source marker in {source}")
    return value


def _safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError("Source marker relative_path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe reconstructed path: {value!r}")
    if path.parts[0] != "brain":
        raise ValueError(f"Reconstructed artifact must remain under brain/: {value!r}")
    return path


def _decode_bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError(f"Invalid base64 in {label}") from exc


def collect_records(bundle: Path) -> list[dict[str, Any]]:
    """Collect and validate all embedded source records in a bundle."""
    root = bundle.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle}")
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    records: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in SOURCE_MARKER_RE.finditer(text):
            record = _decode_record(match.group(1), path)
            record["_marker_file"] = str(path)
            records.append(record)
    if not records:
        raise ValueError(f"No Antigravity source markers found in {bundle}")
    return records


def _prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        sentinel = output / RECONSTRUCTION_SENTINEL
        if not force:
            raise FileExistsError(f"Output already exists (use --force): {output}")
        if not sentinel.is_file():
            raise ValueError(
                f"Refusing to replace a directory not created by this tool: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / RECONSTRUCTION_SENTINEL).write_text("1\n", encoding="utf-8")


def reconstruct(bundle: Path, output: Path, *, force: bool = False) -> dict[str, Any]:
    """Rebuild exact artifact and sidecar bytes from source markers."""
    records = collect_records(bundle)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        artifact_id = record.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ValueError("Source marker is missing artifact_id")
        grouped[artifact_id].append(record)

    planned: list[tuple[PurePosixPath, bytes, str | None, bytes | None]] = []
    seen_paths: set[PurePosixPath] = set()
    for artifact_id, parts in sorted(grouped.items()):
        paths = {_safe_relative_path(item.get("relative_path")) for item in parts}
        if len(paths) != 1:
            raise ValueError(f"Artifact {artifact_id} has conflicting source paths")
        relative_path = paths.pop()
        if relative_path in seen_paths:
            raise ValueError(f"Duplicate reconstructed path: {relative_path}")
        seen_paths.add(relative_path)

        expected_counts = {item.get("part_count") for item in parts}
        if len(expected_counts) != 1:
            raise ValueError(f"Artifact {artifact_id} has conflicting part counts")
        expected_count = expected_counts.pop()
        if not isinstance(expected_count, int) or expected_count < 1:
            raise ValueError(f"Artifact {artifact_id} has invalid part_count")
        if len(parts) != expected_count:
            raise ValueError(
                f"Artifact {artifact_id} has {len(parts)}/{expected_count} parts"
            )

        indices: list[int] = []
        for item in parts:
            index = item.get("part_index")
            if not isinstance(index, int):
                raise ValueError(f"Artifact {artifact_id} has an invalid part index")
            indices.append(index)
        if sorted(indices) != list(range(expected_count)):
            raise ValueError(f"Artifact {artifact_id} has missing or duplicate parts")
        ordered = sorted(parts, key=lambda item: int(item["part_index"]))

        chunks: list[bytes] = []
        metadata_name: str | None = None
        metadata: bytes | None = None
        for item in ordered:
            chunk = _decode_bytes(item.get("content_b64"), "content_b64")
            expected_hash = item.get("content_sha256")
            actual_hash = hashlib.sha256(chunk).hexdigest()
            if expected_hash != actual_hash:
                raise ValueError(f"Artifact {artifact_id} failed its chunk hash check")
            chunks.append(chunk)
            if item.get("metadata_b64") is not None:
                if metadata is not None:
                    raise ValueError(f"Artifact {artifact_id} repeats its metadata")
                metadata = _decode_bytes(item["metadata_b64"], "metadata_b64")
                candidate = item.get("metadata_name")
                if not isinstance(candidate, str) or not candidate:
                    raise ValueError(f"Artifact {artifact_id} metadata has no filename")
                if Path(candidate).name != candidate:
                    raise ValueError(f"Unsafe metadata filename: {candidate!r}")
                metadata_name = candidate
        planned.append((relative_path, b"".join(chunks), metadata_name, metadata))

    _prepare_output(output, force)
    written = 0
    for relative_path, content, metadata_name, metadata in planned:
        destination = output.joinpath(*relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        written += 1
        if metadata is not None and metadata_name is not None:
            (destination.parent / metadata_name).write_bytes(metadata)
            written += 1

    report = {
        "artifacts_reconstructed": len(planned),
        "files_written": written,
        "source_markers": len(records),
        "byte_exact": True,
    }
    (output / "reconstruction-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.bundle, args.output, force=args.force), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

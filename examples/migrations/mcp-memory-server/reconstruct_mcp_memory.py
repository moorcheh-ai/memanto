#!/usr/bin/env python3
"""Reconstruct MCP Memory JSONL from the lossless blocks in an OKF bundle."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from migrate_mcp_memory import MigrationError

_SOURCE_BLOCK = re.compile(
    r"(?P<fence>`{3,})json mcp-memory-source[^\n]*\n"
    r"(?P<payload>.*?)\n(?P=fence)(?:\n|$)",
    re.DOTALL,
)


def _source_payloads(okf_path: str | Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load every embedded MCP source payload from an OKF bundle."""
    root = Path(okf_path)
    memories = root / "memories" if (root / "memories").is_dir() else root
    payloads: list[tuple[Path, dict[str, Any]]] = []

    for file_path in sorted(memories.rglob("*.md")):
        text = file_path.read_text(encoding="utf-8")
        match = _SOURCE_BLOCK.search(text)
        if not match:
            continue
        try:
            payload = json.loads(match.group("payload"))
        except json.JSONDecodeError as exc:
            raise MigrationError(
                f"{file_path}: invalid lossless MCP source block"
            ) from exc
        if not isinstance(payload, dict):
            raise MigrationError(f"{file_path}: source block must be an object")
        payloads.append((file_path, payload))

    if not payloads:
        raise MigrationError("bundle contains no lossless MCP source blocks")
    return payloads


def _records_from_payloads(
    payloads: list[tuple[Path, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Reassemble parsed records in their original source-line order."""
    indexed: dict[int, dict[str, Any]] = {}

    for file_path, payload in payloads:
        entries = [payload.get("entity")]
        relations = payload.get("outgoing_relations", [])
        if not isinstance(relations, list):
            raise MigrationError(f"{file_path}: outgoing_relations must be an array")
        entries.extend(relations)
        for entry in entries:
            if not isinstance(entry, dict):
                raise MigrationError(f"{file_path}: malformed indexed record")
            line = entry.get("line")
            record = entry.get("record")
            if not isinstance(line, int) or not isinstance(record, dict):
                raise MigrationError(f"{file_path}: malformed indexed record")
            if line in indexed:
                raise MigrationError(
                    f"{file_path}: duplicate original source line {line}"
                )
            indexed[line] = record

    if not indexed:
        raise MigrationError("bundle contains no indexed MCP source records")
    return [indexed[line] for line in sorted(indexed)]


def reconstruct_records(okf_path: str | Path) -> list[dict[str, Any]]:
    """Return parsed MCP records in their exact original line order."""
    return _records_from_payloads(_source_payloads(okf_path))


def _decode_exact_source(
    payloads: list[tuple[Path, dict[str, Any]]],
) -> tuple[bytes, list[dict[str, Any]]] | None:
    """Decode and validate the single exact-source manifest, when present."""
    manifests: list[tuple[Path, dict[str, Any]]] = []
    for file_path, payload in payloads:
        manifest = payload.get("source_file")
        if manifest is None:
            continue
        if not isinstance(manifest, dict):
            raise MigrationError(f"{file_path}: source_file must be an object")
        manifests.append((file_path, manifest))

    if not manifests:
        return None
    if len(manifests) != 1:
        raise MigrationError("bundle contains multiple exact MCP source manifests")

    file_path, manifest = manifests[0]
    encoded = manifest.get("bytes")
    expected_sha = manifest.get("sha256")
    if manifest.get("encoding") != "base64":
        raise MigrationError(f"{file_path}: unsupported exact-source encoding")
    if not isinstance(encoded, str) or not isinstance(expected_sha, str):
        raise MigrationError(f"{file_path}: malformed exact MCP source manifest")
    try:
        source_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MigrationError(f"{file_path}: invalid exact-source base64") from exc
    actual_sha = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha != expected_sha:
        raise MigrationError(f"{file_path}: exact MCP source hash mismatch")

    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MigrationError("exact MCP source manifest must contain UTF-8") from exc
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(source_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise MigrationError(
                f"exact MCP source line {line_number}: invalid JSON"
            ) from exc
        if not isinstance(record, dict):
            raise MigrationError(
                f"exact MCP source line {line_number}: record must be an object"
            )
        records.append(record)
    return source_bytes, records


def reconstructed_jsonl(okf_path: str | Path) -> bytes:
    """Reconstruct the original JSONL bytes, including formatting and EOF state."""
    payloads = _source_payloads(okf_path)
    records = _records_from_payloads(payloads)
    exact_source = _decode_exact_source(payloads)
    if exact_source is not None:
        source_bytes, source_records = exact_source
        if source_records != records:
            raise MigrationError(
                "exact MCP source manifest does not match indexed records"
            )
        return source_bytes

    raise MigrationError(
        "bundle is missing the exact MCP source manifest required for "
        "byte-lossless reconstruction"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct MCP Memory JSONL from an OKF bundle."
    )
    parser.add_argument("--input", required=True, help="Generated OKF directory")
    parser.add_argument("--output", required=True, help="Reconstructed JSONL path")
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        print(f"error: output already exists: {output}")
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.write_bytes(reconstructed_jsonl(args.input))
    except MigrationError as exc:
        print(f"error: {exc}")
        return 2
    print(f"reconstructed {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

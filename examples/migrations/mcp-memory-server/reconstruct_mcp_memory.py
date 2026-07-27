#!/usr/bin/env python3
"""Reconstruct MCP Memory JSONL from the lossless blocks in an OKF bundle."""

from __future__ import annotations

import argparse
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


def reconstruct_records(okf_path: str | Path) -> list[dict[str, Any]]:
    root = Path(okf_path)
    memories = root / "memories" if (root / "memories").is_dir() else root
    indexed: dict[int, dict[str, Any]] = {}

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
        raise MigrationError("bundle contains no lossless MCP source blocks")
    return [indexed[line] for line in sorted(indexed)]


def reconstructed_jsonl(okf_path: str | Path) -> bytes:
    lines = [
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in reconstruct_records(okf_path)
    ]
    return ("\n".join(lines)).encode("utf-8")


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

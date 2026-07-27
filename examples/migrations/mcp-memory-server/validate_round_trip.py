#!/usr/bin/env python3
"""Validate source fidelity and Memanto OKF consumability without API access."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from migrate_mcp_memory import MigrationError, load_mcp_graph
from reconstruct_mcp_memory import reconstructed_jsonl


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_memanto_rows(okf_path: Path) -> list[dict[str, Any]]:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    return map_okf(load_okf_bundle(okf_path))


def _source_text(graph: Any) -> str:
    parts: list[str] = []
    for entity in graph.entities:
        parts.extend([entity.name, entity.entity_type, *entity.observations])
    for relation in graph.relations:
        parts.extend([relation.source, relation.target, relation.relation_type])
    return "\n".join(parts).casefold()


def validate(
    source_path: str | Path,
    okf_path: str | Path,
    golden_path: str | Path,
) -> dict[str, Any]:
    graph = load_mcp_graph(source_path)
    okf_root = Path(okf_path)
    rows = _load_memanto_rows(okf_root)

    reconstructed = reconstructed_jsonl(okf_root)
    if reconstructed != graph.source_bytes:
        raise MigrationError("lossless reconstruction does not match source bytes")
    if len(rows) != len(graph.entities):
        raise MigrationError(
            f"Memanto mapped {len(rows)} rows for {len(graph.entities)} entities"
        )

    source_text = _source_text(graph)
    imported_text = "\n".join(
        f"{row.get('title', '')}\n{row.get('content', '')}" for row in rows
    ).casefold()
    golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    if not isinstance(golden, list):
        raise MigrationError("golden Q&A file must contain an array")

    results: list[dict[str, Any]] = []
    for item in golden:
        if not isinstance(item, dict):
            raise MigrationError("golden Q&A entries must be objects")
        question = item.get("question")
        phrases = item.get("required_phrases")
        if not isinstance(question, str) or not isinstance(phrases, list):
            raise MigrationError("golden Q&A entry is malformed")
        normalized = [str(phrase).casefold() for phrase in phrases]
        before = all(phrase in source_text for phrase in normalized)
        after = all(phrase in imported_text for phrase in normalized)
        results.append(
            {
                "question": question,
                "source_phrase_retained": before,
                "memanto_okf_phrase_retained": after,
            }
        )

    passed = sum(
        bool(item["source_phrase_retained"] and item["memanto_okf_phrase_retained"])
        for item in results
    )
    summary = {
        "source_sha256": graph.source_sha256,
        "reconstructed_sha256": hashlib.sha256(reconstructed).hexdigest(),
        "source_records_reconstructed": len(graph.entities) + len(graph.relations),
        "memanto_rows_mapped": len(rows),
        "golden_phrase_checks": len(results),
        "phrase_retention_passed": passed,
        "phrase_retention_percent": round(
            (passed / len(results) * 100) if results else 100.0, 2
        ),
        "results": results,
    }
    if passed != len(results):
        raise MigrationError(f"phrase retention failed: {passed}/{len(results)} checks")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate MCP Memory → OKF round-trip fidelity."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--okf", required=True)
    parser.add_argument("--golden", required=True)
    parser.add_argument("--report", help="Optional JSON report output")
    args = parser.parse_args()
    try:
        summary = validate(args.source, args.okf, args.golden)
    except (MigrationError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

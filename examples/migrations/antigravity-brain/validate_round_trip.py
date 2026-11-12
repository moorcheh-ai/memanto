#!/usr/bin/env python3
"""Validate Antigravity → OKF fidelity and Memanto consumability."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from migrate_antigravity import discover_artifacts, sha256_bytes
from reconstruct_antigravity import reconstruct


def _source_files(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for artifact in discover_artifacts(source):
        files[artifact.relative_path.as_posix()] = artifact.content
        if artifact.metadata is not None and artifact.metadata_name is not None:
            metadata_path = artifact.relative_path.parent / artifact.metadata_name
            files[metadata_path.as_posix()] = artifact.metadata
    return files


def _load_goldens(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Golden validation file must contain a JSON list")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each golden validation case must be an object")
        if not isinstance(item.get("question"), str):
            raise ValueError("Each golden validation case needs a question")
        phrases = item.get("expected_phrases")
        if (
            not isinstance(phrases, list)
            or not phrases
            or not all(isinstance(phrase, str) and phrase for phrase in phrases)
        ):
            raise ValueError("Each golden validation case needs expected_phrases")
    return value


def validate(source: Path, bundle: Path, goldens: Path) -> dict[str, Any]:
    """Prove exact local reconstruction and content retention through Memanto."""
    expected = _source_files(source)
    with tempfile.TemporaryDirectory(prefix="antigravity-reconstructed-") as temp:
        reconstruction_root = Path(temp) / "archive"
        reconstruction = reconstruct(bundle, reconstruction_root)
        actual = {
            str(path.relative_to(reconstruction_root)).replace(
                "\\", "/"
            ): path.read_bytes()
            for path in reconstruction_root.rglob("*")
            if path.is_file()
            and path.name
            not in {".antigravity-reconstruction-v1", "reconstruction-report.json"}
        }

    exact_paths = sorted(
        path for path, data in expected.items() if actual.get(path) == data
    )
    unexpected_paths = sorted(set(actual) - set(expected))
    missing_or_changed = sorted(
        path for path, data in expected.items() if actual.get(path) != data
    )
    if missing_or_changed or unexpected_paths:
        raise ValueError(
            "Round-trip mismatch: "
            f"missing_or_changed={missing_or_changed}, unexpected={unexpected_paths}"
        )

    from memanto.cli.migrate.mappers import map_okf, type_breakdown
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    export = load_okf_bundle(bundle)
    rows = map_okf(export)
    if len(rows) != len(export.get("memories", [])):
        raise ValueError("Memanto mapper skipped one or more OKF memories")

    source_text = "\n".join(
        data.decode("utf-8", errors="ignore") for data in expected.values()
    ).casefold()
    mapped_text = "\n".join(
        f"{row.get('title', '')}\n{row.get('content', '')}" for row in rows
    ).casefold()
    cases = []
    for item in _load_goldens(goldens):
        phrases = item["expected_phrases"]
        source_hits = [phrase for phrase in phrases if phrase.casefold() in source_text]
        mapped_hits = [phrase for phrase in phrases if phrase.casefold() in mapped_text]
        cases.append(
            {
                "question": item["question"],
                "expected_phrases": phrases,
                "source_hits": len(source_hits),
                "mapped_hits": len(mapped_hits),
                "passed": len(mapped_hits) == len(phrases) == len(source_hits),
            }
        )
    failed = [case["question"] for case in cases if not case["passed"]]
    if failed:
        raise ValueError(f"Golden phrase retention failed: {failed}")

    expected_digest = sha256_bytes(
        b"".join(path.encode() + b"\0" + expected[path] for path in sorted(expected))
    )
    actual_digest = sha256_bytes(
        b"".join(path.encode() + b"\0" + actual[path] for path in sorted(actual))
    )
    return {
        "source_files": len(expected),
        "files_reconstructed_exactly": len(exact_paths),
        "source_tree_sha256": expected_digest,
        "reconstructed_tree_sha256": actual_digest,
        "byte_exact": expected_digest == actual_digest,
        "source_markers": reconstruction["source_markers"],
        "memanto_okf_entries": len(export.get("memories", [])),
        "memanto_rows_mapped": len(rows),
        "memanto_type_breakdown": type_breakdown(rows),
        "golden_cases": cases,
        "golden_cases_passed": len(cases),
        "golden_phrase_retention_percent": 100.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("goldens", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.source, args.bundle, args.goldens), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

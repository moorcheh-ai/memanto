#!/usr/bin/env python3
"""Verify bundle checksums, import scope, counts, and replay fidelity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import adapter


def verify_bundle(bundle: str | Path) -> dict[str, object]:
    root = Path(bundle).resolve()
    manifest_path = root / "migration-manifest.json"
    if not manifest_path.is_file():
        raise adapter.AdapterError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != adapter.MANIFEST_SCHEMA:
        raise adapter.AdapterError("Unexpected migration manifest schema")

    failures = []
    for expected in manifest.get("files", []):
        path = root / expected["path"]
        if not path.is_file():
            failures.append(f"missing: {expected['path']}")
            continue
        if path.stat().st_size != expected["bytes"]:
            failures.append(f"size: {expected['path']}")
        if adapter.sha256_file(path) != expected["sha256"]:
            failures.append(f"sha256: {expected['path']}")

    snapshot_path = root / manifest["source"]["snapshot_path"]
    snapshot = adapter.load_snapshot(snapshot_path)
    concepts = adapter.build_concepts(snapshot)
    expected_count = manifest["migration"]["mapped_memories"]
    if len(concepts) != expected_count:
        failures.append(
            f"replay count: expected {expected_count}, reconstructed {len(concepts)}"
        )

    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    mapped = map_okf(load_okf_bundle(root))
    if len(mapped) != expected_count:
        failures.append(
            f"Memanto import count: expected {expected_count}, loaded {len(mapped)}"
        )
    mapped_by_ref = {row.get("source_ref"): row for row in mapped}
    for concept in concepts:
        active = mapped_by_ref.get(concept["resource"])
        if active is None:
            failures.append(f"missing mapped resource: {concept['resource']}")
            continue
        for update in concept["history"][:-1]:
            old_value = update.get("value")
            if (
                isinstance(old_value, str)
                and len(old_value) >= 20
                and old_value in active["content"]
            ):
                failures.append(
                    f"superseded value leaked into active memory: {concept['id']}"
                )

    return {
        "schema": "google-adk-artifact-verification/v1",
        "bundle": root.name,
        "files_checked": len(manifest.get("files", [])),
        "mapped_memories": len(mapped),
        "replayed_concepts": len(concepts),
        "failures": failures,
        "passed": not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify_bundle(args.bundle)
    except (OSError, ValueError, adapter.AdapterError) as exc:
        print(f"error: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

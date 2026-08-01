#!/usr/bin/env python3
"""Verify bundle checksums, import scope, counts, and replay fidelity."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import adapter


def _contains_meaningful_value(content: str, value: object) -> bool:
    """Match superseded scalar or structured values in primary memory content."""
    primary_content = content.partition("[Supporting data]")[0]
    if adapter._is_redacted_only(value):
        return False
    if isinstance(value, str):
        candidate = value.strip()
        if len(candidate) < 3:
            return False
        return (
            re.search(
                rf"(?<!\w){re.escape(candidate)}(?!\w)",
                primary_content,
                flags=re.IGNORECASE,
            )
            is not None
        )

    if isinstance(value, dict):
        raw_content = value.get("content", value.get("text", value.get("value")))
        if raw_content not in (None, ""):
            rendered = adapter._content_from_value("State value", value)[1].strip()
            if adapter._is_redacted_only(rendered):
                return False
            return (
                re.search(
                    rf"(?<!\w){re.escape(rendered)}(?!\w)",
                    primary_content,
                    flags=re.IGNORECASE,
                )
                is not None
            )

    candidate = adapter.canonical_json(value)
    if isinstance(value, (dict, list)):
        normalized_content = re.sub(r"\s+", "", primary_content).casefold()
        return candidate.casefold() in normalized_content
    return (
        re.search(
            rf"(?<![\w.]){re.escape(candidate)}(?![\w.])",
            primary_content,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _manifest_path(root: Path, value: object, *, label: str) -> Path:
    """Resolve a manifest path without allowing it to escape the bundle."""
    if not isinstance(value, str) or not value:
        raise adapter.AdapterError(f"Invalid {label}: expected a relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise adapter.AdapterError(f"Unsafe {label}: {value}")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise adapter.AdapterError(f"Unsafe {label}: {value}") from exc
    if resolved == resolved_root:
        raise adapter.AdapterError(f"Unsafe {label}: {value}")
    return resolved


def verify_bundle(bundle: str | Path) -> dict[str, object]:
    root = Path(bundle).resolve()
    manifest_path = root / "migration-manifest.json"
    if not manifest_path.is_file():
        raise adapter.AdapterError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise adapter.AdapterError("Migration manifest must be a JSON object")
    if manifest.get("schema") != adapter.MANIFEST_SCHEMA:
        raise adapter.AdapterError("Unexpected migration manifest schema")

    failures = []
    expected_files = manifest.get("files")
    if not isinstance(expected_files, list):
        raise adapter.AdapterError("Manifest files must be a JSON array")
    seen_paths: set[str] = set()
    for index, expected in enumerate(expected_files):
        if not isinstance(expected, dict):
            raise adapter.AdapterError(f"Invalid manifest file entry at index {index}")
        expected_path = expected.get("path")
        expected_bytes = expected.get("bytes")
        expected_sha256 = expected.get("sha256")
        if (
            not isinstance(expected_bytes, int)
            or expected_bytes < 0
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise adapter.AdapterError(
                f"Invalid manifest metadata for file entry at index {index}"
            )
        if not isinstance(expected_path, str) or expected_path in seen_paths:
            raise adapter.AdapterError(
                f"Invalid or duplicate manifest path at file entry {index}"
            )
        seen_paths.add(expected_path)
        path = _manifest_path(root, expected_path, label="manifest file path")
        if not path.is_file():
            failures.append(f"missing: {expected_path}")
            continue
        if path.stat().st_size != expected_bytes:
            failures.append(f"size: {expected_path}")
        if adapter.sha256_file(path) != expected_sha256:
            failures.append(f"sha256: {expected_path}")

    expected_memory_files = {
        path
        for path in seen_paths
        if path == "memories" or path.startswith("memories/")
    }
    actual_memory_files = {
        path.relative_to(root).as_posix()
        for path in (root / "memories").rglob("*")
        if path.is_file()
    }
    for extra_path in sorted(actual_memory_files - expected_memory_files):
        failures.append(f"unlisted memory file: {extra_path}")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise adapter.AdapterError("Manifest source must be a JSON object")
    snapshot_path = _manifest_path(
        root, source.get("snapshot_path"), label="source snapshot path"
    )
    snapshot_sha256 = source.get("snapshot_sha256")
    if (
        not isinstance(snapshot_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256) is None
    ):
        raise adapter.AdapterError("Invalid source snapshot SHA-256")
    if not snapshot_path.is_file():
        raise adapter.AdapterError(f"Source snapshot not found: {snapshot_path}")
    if adapter.sha256_file(snapshot_path) != snapshot_sha256:
        failures.append("sha256: source snapshot")

    migration = manifest.get("migration")
    if not isinstance(migration, dict):
        raise adapter.AdapterError("Manifest migration must be a JSON object")
    expected_count = migration.get("mapped_memories")
    if not isinstance(expected_count, int) or expected_count < 0:
        raise adapter.AdapterError("Invalid mapped memory count")

    snapshot = adapter.load_snapshot(snapshot_path)
    concepts = adapter.build_concepts(snapshot)
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
            if _contains_meaningful_value(active["content"], old_value):
                failures.append(
                    f"superseded value leaked into active memory: {concept['id']}"
                )

    for memory_path in (root / "memories").rglob("*.md"):
        text = memory_path.read_text(encoding="utf-8")
        for target in re.findall(r"\[Audit trail[^]]*\]\(([^)]+)\)", text):
            try:
                relative = Path(target)
                if relative.is_absolute():
                    raise ValueError
                audit_path = (memory_path.parent / relative).resolve()
                audit_path.relative_to(root)
            except ValueError:
                failures.append(
                    f"unsafe audit link: {memory_path.relative_to(root).as_posix()}"
                )
                continue
            if not audit_path.is_file():
                failures.append(
                    "missing audit link target: "
                    f"{memory_path.relative_to(root).as_posix()} -> {target}"
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

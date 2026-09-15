"""Run a real local conversion, official CLI preview and format round trip.

This script deliberately does not substitute a fake backend for a live import.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from adapter import (
    build_bundle,
    canonical,
    digest,
    load_catalog,
    restore_bundle,
    restore_contents,
    select_catalog,
)

from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def execute(source: Path, output: Path, public_only: bool) -> dict:
    data = load_catalog(source)
    selected = select_catalog(data, public_only)
    output.mkdir(parents=True, exist_ok=False)
    print(f"Source: {len(data['tiles'])} real saved invention tiles", flush=True)
    summary = build_bundle(data, output / "input_okf", public_only=public_only)
    print(
        f"Selected: {summary['selected_tiles']} tiles; excluded: {summary['excluded_tiles']}",
        flush=True,
    )
    print("Running the unmodified Memanto CLI import preview...", flush=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "memanto.cli.main",
            "migrate",
            "okf",
            str(output / "input_okf"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    (output / "official_cli_preview.txt").write_text(
        proc.stdout + proc.stderr, encoding="utf-8"
    )
    print(proc.stdout, flush=True)
    if proc.returncode:
        raise RuntimeError("Official CLI preview failed; see official_cli_preview.txt")
    loaded = load_okf_bundle(output / "input_okf")
    mapped = map_okf(loaded)
    if len(mapped) != summary["okf_memories"]:
        raise AssertionError("Official mapper skipped or added records")
    mapped_restored = restore_contents([r["content"] for r in mapped])
    if mapped_restored != selected:
        raise AssertionError("Official mapping changed source fields")
    (output / "mapped_preview.json").write_text(
        json.dumps(mapped, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    # These records are passed to the real serialization service, not stored
    # in Moorcheh. IDs identify local format-test inputs, not remote memories.
    grouped: dict[str, list[dict]] = {}
    for index, row in enumerate(mapped):
        record = dict(row, id=f"local-format-only-{index}")
        grouped.setdefault(row["type"], []).append(record)
    service = OkfExportService(exports_dir=output / "exports")
    exported = service.write_okf_bundle(
        "voller-format-demo", grouped, output_dir=output / "exported_okf", split="type"
    )
    restored = restore_bundle(Path(exported["output_path"]))
    if canonical(restored) != canonical(selected):
        raise AssertionError("Native OKF format round trip lost source information")
    (output / "restored_catalogue.json").write_text(
        json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        **summary,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "memanto_version": importlib.metadata.version("memanto"),
        "official_cli_preview_exit_code": proc.returncode,
        "official_mapped_count": len(mapped),
        "per_type_counts": {k: len(v) for k, v in grouped.items()},
        "all_selected_source_fields_preserved": True,
        "native_format_round_trip_passed": True,
        "restored_sha256": digest(restored),
        "selected_canonical_json_bytes": len(canonical(selected).encode()),
        "input_okf_bytes": sum(
            p.stat().st_size for p in (output / "input_okf").rglob("*.md")
        ),
        "remote_import_executed": False,
        "semantic_recall_tested": False,
        "prize_submission_complete": False,
        "limitations": [
            "Native format serialization was executed locally; no remote memory store was used.",
            "The source is a real Voller Attention Tiles snapshot, not a ChatGPT conversation export.",
            "Checksums check content integrity, not authorship or resistance to malicious rewriting.",
            "No token, cloud-latency, semantic-recall, compression or financial benefit is claimed.",
        ],
    }
    (output / "validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(
        f"PASS: all fields in {len(restored['tiles'])} tiles restored exactly",
        flush=True,
    )
    print(
        "LOCAL FORMAT TEST COMPLETE. Live storage, retrieval and competition entry are still pending.",
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args()
    execute(args.source.resolve(), args.output.resolve(), args.public_only)

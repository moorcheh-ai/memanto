"""
Qdrant -> Memanto -> OKF freedom-loop runner.

Single command that proves the full escape path from a Qdrant-backed memory
store into portable OKF markdown:

    1. Seed a lived-in Qdrant collection (embedded, no infra needed)
    2. Dump it with the ``qdrant_export`` analyzer
    3. Map it through ``map_qdrant`` (dry-run preview + savings-style summary)
    4. Export the mapped memories to a valid OKF bundle
    5. Round-trip validation: golden questions answered from the bundle

Run (from the repo root)::

    python examples/migrations/qdrant-to-okf/run_migration.py

Artifacts land in ``examples/migrations/qdrant-to-okf/output/``:
    export.json              raw Qdrant dump (provider-style export)
    mapped_preview.jsonl     mapped Memanto memory payloads
    okf_bundle/              the OKF bundle (index.md + memories/)
    roundtrip_report.md      golden-QA recall parity report

No Docker, no API keys, no server: the embedded Qdrant instance and the
standalone OKF exporter run the whole loop locally. (To run against a real
server-backed store instead: ``--url http://localhost:6333`` + a seeded
collection — everything downstream is identical.)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (examples/../..)
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent / "output"


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="Qdrant server URL (default: embedded in-memory)")
    parser.add_argument("--collection", default="memories")
    parser.add_argument("--keep-export", action="store_true", help="Reuse existing export.json instead of re-dumping")
    args = parser.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    export_path = OUT / "export.json"

    # 1. Seed + dump -----------------------------------------------------
    if args.keep_export and export_path.exists():
        step("Reusing existing export.json")
        export = json.loads(export_path.read_text(encoding="utf-8"))
    else:
        step("Seeding lived-in Qdrant collection (embedded)")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from seed_qdrant import seed
        from qdrant_client import QdrantClient

        client = QdrantClient(":memory:") if args.url is None else QdrantClient(url=args.url)
        n = seed(client, args.collection)
        print(f"Seeded {n} points in '{args.collection}'")

        step("Dumping Qdrant collection -> provider export")
        from memanto.cli.analyze.qdrant_export import dump_collection

        memories = dump_collection(client, args.collection)
        export = {
            "provider": "qdrant",
            "collection": args.collection,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memories": memories,
        }
        export_path.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Dumped {len(memories)} memories -> {export_path}")

    # 2. Map --------------------------------------------------------------
    step("Mapping through map_qdrant (dry-run preview)")
    from memanto.cli.migrate.mappers import MAPPERS, type_breakdown
    from memanto.cli.migrate.runner import source_count

    provider = "qdrant"
    rows = MAPPERS[provider](export)
    counts = type_breakdown(rows)
    print(f"Source records : {source_count(provider, export)}")
    print(f"Mapped rows    : {len(rows)}")
    print(f"Type breakdown : {json.dumps(counts, indent=2)}")

    preview = OUT / "mapped_preview.jsonl"
    with preview.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    print(f"Mapped rows -> {preview}")

    if not rows:
        raise SystemExit("ERROR: map_qdrant produced 0 rows — nothing to migrate. Check the export payload shape.")

    sample = rows[0]
    print("\nSample mapped row:")
    print(json.dumps({k: v for k, v in sample.items() if k != "content"}, indent=2, ensure_ascii=False, default=str))
    print(f"Content: {sample['content'][:140]}...")

    # 3. OKF bundle ---------------------------------------------------------
    step("Exporting mapped memories -> OKF bundle")
    from memanto.app.services.okf_export_service import OkfExportService

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        t = row.get("type") or "auto"
        by_type.setdefault(t, []).append(
            {
                "title": row.get("title"),
                "content": row.get("content"),
                "type": t,
                "tags": row.get("tags") or [],
                "created_at": row.get("created_at"),
                "source_ref": row.get("source_ref"),
                "id": row.get("source_ref"),
                "confidence": row.get("confidence"),
                "provenance": row.get("provenance"),
                "source": row.get("source"),
            }
        )

    exporter = OkfExportService(exports_dir=OUT / "exports")
    result = exporter.write_okf_bundle(
        agent_id="tim-qdrant-escape",
        memories_by_type=by_type,
        output_dir=OUT / "okf_bundle",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    # 4. Round-trip validation ----------------------------------------------
    step("Round-trip validation (golden QA from the OKF bundle)")
    from memanto.cli.migrate.okf_loader import load_okf_bundle
    from memanto.cli.migrate.mappers import map_okf

    bundle_dir = OUT / "okf_bundle"
    loaded = load_okf_bundle(bundle_dir)
    okf_rows = map_okf(loaded)
    okf_by_type = type_breakdown(okf_rows)
    print(f"OKF bundle re-loaded: {len(okf_rows)} memories re-imported")
    print(f"Round-trip type parity: {counts == okf_by_type or 'types may re-classify on import'}")
    print(f"Re-imported breakdown: {json.dumps(okf_by_type, indent=2)}")

    # Record-level round-trip parity — every source record must come back.
    # Keys on source_ref (record identity); type may re-classify on import, so
    # it is reported, not failed on. Content must survive (footer additions OK).
    from collections import Counter

    src_refs = Counter(str(r.get("source_ref")) for r in rows)
    okf_refs = Counter(str(r.get("source_ref")) for r in okf_rows)
    missing = src_refs - okf_refs
    extra = okf_refs - src_refs

    src_content: dict[str, list[str]] = {}
    for r in rows:
        src_content.setdefault(str(r.get("source_ref")), []).append((r.get("content") or "").strip())
    okf_content: dict[str, list[str]] = {}
    for r in okf_rows:
        okf_content.setdefault(str(r.get("source_ref")), []).append((r.get("content") or "").strip())

    reclassified = []
    for r in okf_rows:
        src = str(r.get("source_ref"))
        orig = next((x.get("type") for x in rows if str(x.get("source_ref")) == src), None)
        if orig and r.get("type") != orig:
            reclassified.append((src, orig, r.get("type")))

    lost = 0
    for ref, bodies in src_content.items():
        for body in bodies:
            if not body:
                continue
            probe = body[:40]
            if not any(probe in (o or "") for o in okf_content.get(ref, [])):
                lost += 1

    record_parity = not missing and not extra and lost == 0
    print(f"Record parity      : {'PASS' if record_parity else 'FAIL'}")
    if missing:
        print(f"  missing {sum(missing.values())} record(s): {dict(missing)}")
    if extra:
        print(f"  extra   {sum(extra.values())} record(s): {dict(extra)}")
    if lost:
        print(f"  {lost} source row(s) lost their content body on re-import")
    if reclassified:
        print(f"  {len(reclassified)} record(s) re-classified on import (informational)")

    # Golden QA — questions answerable from the bundle content
    bundle_text = "\n".join(
        (p.read_text(encoding="utf-8") if p.is_file() else "")
        for p in bundle_dir.rglob("*.md")
    ).lower()
    golden = {
        "Where does Tim live?": "lisbon",
        "What is Tim's cat's name?": "pixel",
        "What embedding store does the team use?": "qdrant",
        "What is the preferred backend language?": "python",
        "What coffee does Tim order?": "flat white",
    }
    hits = 0
    report_lines = [
        "# Round-trip validation report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Source: Qdrant collection '{args.collection}' ({source_count(provider, export)} records)",
        f"Mapped: {len(rows)} memories -> {len(okf_rows)} re-imported from OKF bundle",
        "",
        "## Record-level round-trip parity",
        "",
        "Keys records by `source_ref` (record identity) and checks content continuity.",
        "Type re-classification on import is expected (OKF types are free-form) and reported, not failed.",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Source records | {len(rows)} |",
        f"| Re-imported records | {len(okf_rows)} |",
        f"| Missing (source_ref in source, absent in bundle) | {sum(missing.values())} |",
        f"| Extra (source_ref only in bundle) | {sum(extra.values())} |",
        f"| Rows whose content body was lost | {lost} |",
        f"| Re-classified on import | {len(reclassified)} |",
        f"| **Record parity** | **{'PASS' if record_parity else 'FAIL'}** |",
        "",
        "## Golden QA (recall parity)",
        "",
        "| Question | Expected | Found in bundle |",
        "| --- | --- | --- |",
    ]
    for q, expected in golden.items():
        found = expected in bundle_text
        hits += int(found)
        report_lines.append(f"| {q} | {expected} | {'YES' if found else 'NO'} |")
    report_lines += [
        "",
        f"**Recall parity: {hits}/{len(golden)} ({100 * hits // len(golden)}%)**",
        "",
        "## Artifacts",
        "",
        "- `export.json` — raw Qdrant collection dump (provider-style export)",
        "- `mapped_preview.jsonl` — mapped Memanto memory payloads",
        "- `okf_bundle/` — valid OKF bundle (index.md + memories/)",
    ]
    (OUT / "roundtrip_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Golden QA recall parity: {hits}/{len(golden)} ({100 * hits // len(golden)}%)")
    print(f"\nReport -> {OUT / 'roundtrip_report.md'}")

    print("\n✅ Freedom loop complete: Qdrant -> Memanto -> OKF, all local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

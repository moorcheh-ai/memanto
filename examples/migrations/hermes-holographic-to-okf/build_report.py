#!/usr/bin/env python3
"""Render the Holo-specific migration/fidelity report used by the bounty demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(
    source: dict[str, Any], export: dict[str, Any], fidelity: dict[str, Any]
) -> str:
    per_type = export.get("per_type", {})
    type_rows = (
        "\n".join(f"| `{name}` | {count} |" for name, count in sorted(per_type.items()))
        or "| — | 0 |"
    )
    accounting = export.get("source_accounting", {})
    derived = export.get("derived_not_serialized", {})
    latencies = source.get("source_search_latency_ms") or []
    latency_text = (
        f"median {source.get('source_search_latency_median_ms')} ms across {len(latencies)} probes"
        if latencies
        else "not measured"
    )
    mismatches = fidelity.get("mismatches") or []

    return f"""# Hermes Holographic migration report

## Migration summary

- Source tool: **{source.get("source_tool", "Hermes Holographic")}**
- Source facts: **{export.get("source_facts", 0)}**
- Exported OKF memories: **{export.get("exported_memories", 0)}**
- Skipped canonical facts: **{max(0, export.get("source_facts", 0) - export.get("exported_memories", 0))}**
- Source entities: **{source.get("entity_count", "n/a")}**
- Fact/entity associations: **{source.get("fact_entity_association_count", "n/a")}**
- SQLite integrity check: **{source.get("sqlite_integrity_check", "not recorded")}**
- Source search latency: **{latency_text}**

| Memanto type | Count |
|---|---:|
{type_rows}

## Structural fidelity

- Result: **{fidelity.get("status", "UNKNOWN")}**
- Field assertions checked: **{fidelity.get("checked_fields", 0)}**
- Mismatches: **{len(mismatches)}**
- Holo memories found in bundle: **{fidelity.get("okf_memories", 0)}**

## Physical / logical accounting

| Metric | Bytes / count |
|---|---:|
| Source SQLite file | {export.get("source_sqlite_bytes", 0)} bytes |
| Canonical fact content | {accounting.get("canonical_content_bytes", 0)} bytes |
| Canonical tag strings | {accounting.get("canonical_tag_bytes", 0)} bytes |
| Holo HRR fact vectors | {accounting.get("hrr_vector_bytes", 0)} bytes |
| Holo memory-bank vectors | {accounting.get("memory_bank_vector_bytes", 0)} bytes |
| Exported OKF bundle | {export.get("okf_bundle_bytes", 0)} bytes |
| OKF files | {export.get("bundle_file_count", 0)} |
| Approx. canonical-content tokens (`bytes / 4`) | {export.get("approx_canonical_content_tokens", 0)} |

**Accounting note:** the direct `memanto migrate okf` path does not generate the provider-style Memanto savings report. These numbers are therefore a Holo-specific accounting report. Reductions in SQLite indexes or vector bytes are **not** described as token savings. The token figure above is only a labeled rough estimate for canonical UTF-8 fact content.

## Derived-data policy

- FTS present in source: `{derived.get("facts_fts_present", False)}` → **rebuild**
- Facts carrying HRR vectors: `{derived.get("hrr_vector_fact_count", 0)}` → **rebuild**
- Memory banks: `{derived.get("memory_bank_count", 0)}` → **rebuild**
- Query-time relatedness / contradiction behavior → **validate, do not fabricate as stored history**

## Integrity identifiers

- Source SQLite SHA-256: `{export.get("source_sha256", "n/a")}`
- Bundle manifest SHA-256: `{export.get("bundle_manifest_sha256", "n/a")}`

## Bounded claim

Hermes Holographic canonical facts, trust, timestamps, tags, and entity associations are exported into human-readable OKF and independently checked against the SQLite source. Derived retrieval structures are explicitly rebuilt rather than misrepresented as canonical portable knowledge.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--export-report", type=Path, required=True)
    parser.add_argument("--fidelity-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rendered = build_report(
        _load(args.source_report),
        _load(args.export_report),
        _load(args.fidelity_report),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

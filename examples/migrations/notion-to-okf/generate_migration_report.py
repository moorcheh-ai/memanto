"""
generate_migration_report.py
============================
Generates the committed migration summary + savings report
from the sample Notion export. No API key needed.

Produces:
  migration_report.json  — source/mapped counts, type breakdown, savings
  savings_report.json    — token/storage reduction numbers

Run:
    python generate_migration_report.py
"""

from __future__ import annotations

import hashlib
import json
import sys  # noqa: E402
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # noqa: E402
from notion_adapter import map_notion  # noqa: E402

DATA = HERE / "data" / "notion_export.json"
BUNDLE = HERE / "sample_okf_bundle"


def sha256_dir(path: Path) -> str:
    """Stable SHA-256 over all .md files in a bundle (sorted paths)."""
    h = hashlib.sha256()
    for f in sorted(path.rglob("*.md")):
        h.update(f.read_bytes())
    return h.hexdigest()


def main() -> None:
    export = json.loads(DATA.read_text(encoding="utf-8"))
    pages = export.get("pages", [])
    rows = map_notion(export)

    # Type breakdown
    type_counts: dict[str, int] = {}
    for r in rows:
        k = r.get("type") or "auto"
        type_counts[k] = type_counts.get(k, 0) + 1

    # Token estimates (len//4)
    source_tokens = sum(
        len(p.get("content") or p.get("title") or "") // 4 for p in pages
    )
    mapped_tokens = sum(len(r.get("content", "")) // 4 for r in rows)

    # Storage: source JSON vs OKF bundle
    source_bytes = DATA.stat().st_size
    bundle_bytes = sum(f.stat().st_size for f in BUNDLE.rglob("*.md"))
    bundle_files = len(list(BUNDLE.rglob("*.md")))

    # SHA-256 of bundle
    bundle_hash = sha256_dir(BUNDLE) if BUNDLE.exists() else "bundle not found"

    dbs: list[str] = list(dict.fromkeys(str(p.get("database", "unknown")) for p in pages))
    ts = datetime.now(timezone.utc).isoformat()

    report = {
        "timestamp": ts,
        "source": {
            "tool": "Notion",
            "databases": dbs,
            "pages": len(pages),
            "source_file": "data/notion_export.json",
            "source_bytes": source_bytes,
        },
        "migration": {
            "memories_mapped": len(rows),
            "skipped": len(pages) - len(rows),
            "type_breakdown": type_counts,
        },
        "okf_bundle": {
            "path": "sample_okf_bundle/",
            "files": bundle_files,
            "bundle_bytes": bundle_bytes,
            "bundle_sha256": bundle_hash,
        },
        "savings": {
            "note": "Notion exports have no provider token/latency billing baseline. "
            "Storage and token estimates below are measured from the sample export.",
            "source_tokens_est": source_tokens,
            "mapped_tokens_est": mapped_tokens,
            "token_reduction_pct": round((1 - mapped_tokens / source_tokens) * 100, 1)
            if source_tokens
            else 0,
            "source_storage_bytes": source_bytes,
            "okf_storage_bytes": bundle_bytes,
            "storage_change_pct": round((bundle_bytes / source_bytes - 1) * 100, 1)
            if source_bytes
            else 0,
            "storage_note": "OKF grows vs raw JSON due to readable frontmatter — "
            "this is intentional portability overhead.",
        },
        "validation": {
            "golden_qa_questions": 6,
            "offline_recall": "run: python validate_recall.py --offline",
            "live_recall": "run: python validate_recall.py --agent notion-migration-demo",
        },
    }

    out = HERE / "migration_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    savings = {
        "timestamp": ts,
        "source_tool": "Notion",
        "source_records": len(pages),
        "mapped_memories": len(rows),
        "source_tokens_estimated": source_tokens,
        "memanto_tokens_estimated": mapped_tokens,
        "token_reduction_pct": float(report["savings"]["token_reduction_pct"]),  # type: ignore[index]
        "source_storage_bytes": source_bytes,
        "okf_storage_bytes": bundle_bytes,
        "storage_change_pct": float(report["savings"]["storage_change_pct"]),  # type: ignore[index]
        "disclaimer": "Savings estimates based on character-length token approximation (len//4). "
        "Notion has no provider token billing; no synthetic baseline is claimed.",
    }
    sout = HERE / "savings_report.json"
    sout.write_text(json.dumps(savings, indent=2), encoding="utf-8")

    print(f"✅ Migration report → {out}")
    print(f"✅ Savings report   → {sout}")
    print(f"\nSource: {len(pages)} pages → {len(rows)} memories")
    print(f"Type breakdown: {type_counts}")
    print(
        f"Token estimate: {source_tokens} → {mapped_tokens} ({savings['token_reduction_pct']}% reduction)"
    )
    print(f"Bundle SHA-256: {bundle_hash[:16]}...")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Export Hermes Holographic SQLite memory into a deterministic OKF v0.2 bundle.

The adapter deliberately treats Holo's SQLite database as the source of truth.
Canonical fields are preserved; derived FTS/HRR/bank vectors are declared as
rebuild-only rather than serialized as portable knowledge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CATEGORY_TO_MEMANTO = {
    "user_pref": "preference",
    "project": "fact",
    "tool": "fact",
    "general": "fact",
}

REQUIRED_TABLES = {"facts", "entities", "fact_entities"}
# Leave headroom for Memanto's own small import footer below its 10k content cap.
MAX_PORTABLE_BODY_CHARS = 9000


def _normalize_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _tags(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, (list, tuple)):
        values = [str(v).strip() for v in raw]
    else:
        values = [piece.strip() for piece in str(raw).split(",")]
    return list(dict.fromkeys(v for v in values if v))


def _memory_type(category: Any) -> str:
    return CATEGORY_TO_MEMANTO.get(str(category or "general").strip().lower(), "fact")


def _assert_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = REQUIRED_TABLES - tables
    if missing:
        raise ValueError(
            "Not a supported Hermes Holographic database; missing table(s): "
            + ", ".join(sorted(missing))
        )


def load_holo_snapshot(db_path: str | Path) -> dict[str, Any]:
    """Read canonical Holo records and summarize derived structures."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Holo database not found: {path}")

    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        _assert_schema(conn)
        facts = []
        for row in conn.execute(
            """
            SELECT fact_id, content, category, tags, trust_score,
                   retrieval_count, helpful_count, created_at, updated_at,
                   hrr_vector
            FROM facts
            ORDER BY fact_id
            """
        ):
            entities = [
                dict(entity)
                for entity in conn.execute(
                    """
                    SELECT e.entity_id, e.name, e.entity_type, e.aliases, e.created_at
                    FROM entities e
                    JOIN fact_entities fe ON fe.entity_id = e.entity_id
                    WHERE fe.fact_id = ?
                    ORDER BY e.entity_id
                    """,
                    (row["fact_id"],),
                )
            ]
            facts.append(
                {
                    "fact_id": int(row["fact_id"]),
                    "content": row["content"],
                    "category": row["category"] or "general",
                    "tags": row["tags"] or "",
                    "trust_score": float(row["trust_score"]),
                    "retrieval_count": int(row["retrieval_count"] or 0),
                    "helpful_count": int(row["helpful_count"] or 0),
                    "created_at": _normalize_timestamp(row["created_at"]),
                    "updated_at": _normalize_timestamp(row["updated_at"]),
                    "has_hrr_vector": row["hrr_vector"] is not None,
                    "entities": entities,
                }
            )

        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        memory_bank_count = (
            int(conn.execute("SELECT COUNT(*) FROM memory_banks").fetchone()[0])
            if "memory_banks" in table_names
            else 0
        )
        has_fts = "facts_fts" in table_names
        canonical_content_bytes = int(
            conn.execute(
                "SELECT COALESCE(SUM(LENGTH(CAST(content AS BLOB))), 0) FROM facts"
            ).fetchone()[0]
        )
        canonical_tag_bytes = int(
            conn.execute(
                "SELECT COALESCE(SUM(LENGTH(CAST(tags AS BLOB))), 0) FROM facts"
            ).fetchone()[0]
        )
        hrr_vector_bytes = int(
            conn.execute(
                "SELECT COALESCE(SUM(LENGTH(hrr_vector)), 0) FROM facts"
            ).fetchone()[0]
        )
        memory_bank_vector_bytes = (
            int(
                conn.execute(
                    "SELECT COALESCE(SUM(LENGTH(vector)), 0) FROM memory_banks"
                ).fetchone()[0]
            )
            if "memory_banks" in table_names
            else 0
        )
        return {
            "facts": facts,
            "accounting": {
                "canonical_content_bytes": canonical_content_bytes,
                "canonical_tag_bytes": canonical_tag_bytes,
                "hrr_vector_bytes": hrr_vector_bytes,
                "memory_bank_vector_bytes": memory_bank_vector_bytes,
            },
            "derived": {
                "facts_fts_present": has_fts,
                "hrr_vector_fact_count": sum(f["has_hrr_vector"] for f in facts),
                "memory_bank_count": memory_bank_count,
            },
        }
    finally:
        conn.close()


def _source_footer(fact: dict[str, Any]) -> str:
    source_data = {
        "schema": "hermes-holographic-v1",
        "fact_id": fact["fact_id"],
        "category": fact["category"],
        "raw_tags": fact["tags"],
        "retrieval_count": fact["retrieval_count"],
        "helpful_count": fact["helpful_count"],
        "entities": [
            {
                "entity_id": e["entity_id"],
                "name": e["name"],
                "entity_type": e["entity_type"],
                "aliases": e["aliases"],
                "created_at": _normalize_timestamp(e["created_at"]),
            }
            for e in fact["entities"]
        ],
        "derived": {
            "hrr_vector": "rebuild" if fact["has_hrr_vector"] else "absent",
            "fts_index": "rebuild",
            "memory_bank_vector": "rebuild",
        },
    }
    rendered = yaml.safe_dump(
        source_data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    return (
        "\n\n---\n\n"
        "## Hermes Holographic source data\n\n"
        "The block below preserves source metadata. Derived retrieval vectors are "
        "rebuild-only and are not portable source truth.\n\n"
        "```yaml\n"
        f"{rendered}\n"
        "```"
    )


def _render_doc(fact: dict[str, Any]) -> tuple[str, str]:
    memory_type = _memory_type(fact["category"])
    title = (
        str(fact["content"]).strip().splitlines()[0][:100]
        or f"Holo fact {fact['fact_id']}"
    )
    frontmatter: dict[str, Any] = {
        "type": memory_type,
        "title": title,
    }
    parsed_tags = _tags(fact["tags"])
    if parsed_tags:
        frontmatter["tags"] = parsed_tags
    if fact["created_at"]:
        frontmatter["timestamp"] = fact["created_at"]
    frontmatter["x_memanto"] = {
        "type": memory_type,
        "confidence": fact["trust_score"],
        "source": "hermes-holographic",
        "provenance": "imported",
        "updated_at": fact["updated_at"],
    }
    front = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    body = str(fact["content"]).strip() + _source_footer(fact)
    if len(body) > MAX_PORTABLE_BODY_CHARS:
        raise ValueError(
            f"Holo fact {fact['fact_id']} would exceed the safe Memanto content limit "
            f"after source metadata is preserved ({len(body)} chars > "
            f"{MAX_PORTABLE_BODY_CHARS}). Refusing to truncate source truth."
        )
    return memory_type, f"---\n{front}\n---\n\n{body}\n"


def _write_index(root: Path, counts: Counter[str]) -> None:
    root_index = [
        "---",
        'okf_version: "0.2"',
        "---",
        "",
        "# Hermes Holographic memory — portable OKF bundle",
        "",
        "Generated from the canonical SQLite fact store. HRR vectors, FTS rows, and",
        "memory-bank vectors are intentionally rebuilt rather than serialized.",
        "",
        "## Memories",
        "",
    ]
    for mem_type in sorted(counts):
        root_index.append(
            f"- [{mem_type}](memories/{mem_type}/index.md) — {counts[mem_type]} memories"
        )
    root_index.append("")
    (root / "index.md").write_text("\n".join(root_index), encoding="utf-8")

    memories = root / "memories"
    memories.mkdir(exist_ok=True)
    mem_index = ["# Memories", ""]
    for mem_type in sorted(counts):
        mem_index.append(f"- [{mem_type}]({mem_type}/index.md)")
    mem_index.append("")
    (memories / "index.md").write_text("\n".join(mem_index), encoding="utf-8")

    for mem_type in sorted(counts):
        type_dir = memories / mem_type
        links = [
            f"- [Holo fact {path.stem.split('-')[-1]}]({path.name})"
            for path in sorted(type_dir.glob("fact-*.md"))
        ]
        (type_dir / "index.md").write_text(
            "\n".join([f"# {mem_type} ({counts[mem_type]})", "", *links, ""]),
            encoding="utf-8",
        )


def export_holo_to_okf(db_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Export a Holo database to OKF and return an evidence-oriented summary."""
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    snapshot = load_holo_snapshot(db_path)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=str(output_dir.parent))
    )
    try:
        counts: Counter[str] = Counter()
        for fact in snapshot["facts"]:
            mem_type, doc = _render_doc(fact)
            type_dir = staging / "memories" / mem_type
            type_dir.mkdir(parents=True, exist_ok=True)
            (type_dir / f"fact-{fact['fact_id']:06d}.md").write_text(
                doc, encoding="utf-8"
            )
            counts[mem_type] += 1

        _write_index(staging, counts)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    source_size = db_path.stat().st_size
    source_sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
    bundle_files = sorted(p for p in output_dir.rglob("*") if p.is_file())
    okf_size = sum(p.stat().st_size for p in bundle_files)
    manifest = "\n".join(
        f"{p.relative_to(output_dir).as_posix()} {hashlib.sha256(p.read_bytes()).hexdigest()}"
        for p in bundle_files
    ).encode("utf-8")
    bundle_manifest_sha256 = hashlib.sha256(manifest).hexdigest()
    report = {
        "source": "hermes-holographic",
        "source_facts": len(snapshot["facts"]),
        "exported_memories": sum(counts.values()),
        "per_type": dict(sorted(counts.items())),
        "source_sqlite_bytes": source_size,
        "source_sha256": source_sha256,
        "okf_bundle_bytes": okf_size,
        "bundle_file_count": len(bundle_files),
        "bundle_manifest_sha256": bundle_manifest_sha256,
        "source_accounting": snapshot["accounting"],
        "approx_canonical_content_tokens": (
            snapshot["accounting"]["canonical_content_bytes"] + 3
        )
        // 4,
        "derived_not_serialized": snapshot["derived"],
        "fidelity_policy": {
            "canonical": "preserve",
            "derived": "rebuild",
            "inferred": "validate-not-serialize",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path, help="Hermes Holographic memory_store.db")
    parser.add_argument("output", type=Path, help="Destination OKF bundle directory")
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    report = export_holo_to_okf(args.db, args.output)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

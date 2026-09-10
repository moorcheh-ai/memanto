#!/usr/bin/env python3
"""Validate structural fidelity of a Hermes Holographic -> OKF bundle.

This validator is intentionally independent of ``export_holo.py``. It reads the
SQLite source and Markdown output directly, checks every portable source field,
and can additionally feed the bundle through Memanto's current OKF loader/mapper.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

_FRONT = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_SOURCE = re.compile(
    r"## Hermes Holographic source data.*?```yaml\n(.*?)\n```", re.DOTALL
)
CATEGORY_TO_MEMANTO = {
    "user_pref": "preference",
    "project": "fact",
    "tool": "fact",
    "general": "fact",
}


def _norm_ts(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "T")
    if "+00:00" in text:
        text = text.replace("+00:00", "Z")
    elif not text.endswith("Z"):
        text += "Z"
    return text


def _source_rows(db: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        facts = []
        for row in conn.execute(
            "SELECT fact_id, content, category, tags, trust_score, retrieval_count, "
            "helpful_count, created_at, updated_at, hrr_vector FROM facts ORDER BY fact_id"
        ):
            entities = [
                dict(e)
                for e in conn.execute(
                    "SELECT e.entity_id, e.name, e.entity_type, e.aliases, e.created_at "
                    "FROM entities e JOIN fact_entities fe ON fe.entity_id=e.entity_id "
                    "WHERE fe.fact_id=? ORDER BY e.entity_id",
                    (row["fact_id"],),
                )
            ]
            facts.append({**dict(row), "entities": entities})
        return facts
    finally:
        conn.close()


def _parse_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    match = _FRONT.match(text)
    if not match:
        raise ValueError(f"missing YAML frontmatter: {path}")
    front = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    source_match = _SOURCE.search(body)
    if not source_match:
        raise ValueError(f"missing Holo source block: {path}")
    source = yaml.safe_load(source_match.group(1)) or {}
    content = body.split("\n\n---\n\n## Hermes Holographic source data", 1)[0].strip()
    return {"front": front, "source": source, "content": content}


def _normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": int(entity["entity_id"]),
        "name": entity["name"],
        "entity_type": entity["entity_type"],
        "aliases": entity["aliases"],
        "created_at": _norm_ts(entity["created_at"]),
    }


def validate(
    db: Path, bundle: Path, memanto_repo: Path | None = None
) -> dict[str, Any]:
    source = _source_rows(db)
    docs: dict[int, tuple[Path, dict[str, Any]]] = {}
    non_holo_docs: list[str] = []
    for path in sorted((bundle / "memories").rglob("*.md")):
        if path.name.lower() == "index.md":
            continue
        try:
            parsed = _parse_doc(path)
        except ValueError as exc:
            if "missing Holo source block" in str(exc):
                non_holo_docs.append(str(path.relative_to(bundle)))
                continue
            raise
        fid = int(parsed["source"]["fact_id"])
        if fid in docs:
            raise ValueError(f"duplicate Holo fact_id {fid} in OKF bundle")
        docs[fid] = (path, parsed)

    mismatches: list[str] = []
    if non_holo_docs:
        mismatches.append(
            "non-Holo memories present in fresh destination: "
            + ", ".join(non_holo_docs)
        )
    per_type: Counter[str] = Counter()
    checked_fields = 0

    for fact in source:
        fid = int(fact["fact_id"])
        if fid not in docs:
            mismatches.append(f"fact {fid}: missing from OKF")
            continue
        _, doc = docs[fid]
        front, src = doc["front"], doc["source"]
        expected_type = CATEGORY_TO_MEMANTO.get(str(fact["category"]), "fact")
        expected_tags = [
            t.strip() for t in str(fact["tags"] or "").split(",") if t.strip()
        ]
        checks = {
            "content": (doc["content"], fact["content"]),
            "type": (front.get("type"), expected_type),
            "tags": (front.get("tags", []), expected_tags),
            "confidence": (
                front.get("x_memanto", {}).get("confidence"),
                float(fact["trust_score"]),
            ),
            "source": (front.get("x_memanto", {}).get("source"), "hermes-holographic"),
            "provenance": (front.get("x_memanto", {}).get("provenance"), "imported"),
            "created_at": (
                _norm_ts(front.get("timestamp")),
                _norm_ts(fact["created_at"]),
            ),
            "updated_at": (
                _norm_ts(front.get("x_memanto", {}).get("updated_at")),
                _norm_ts(fact["updated_at"]),
            ),
            "category": (src.get("category"), fact["category"]),
            "raw_tags": (src.get("raw_tags", ""), fact["tags"] or ""),
            "retrieval_count": (
                src.get("retrieval_count"),
                int(fact["retrieval_count"] or 0),
            ),
            "helpful_count": (
                src.get("helpful_count"),
                int(fact["helpful_count"] or 0),
            ),
            "entities": (
                src.get("entities", []),
                [_normalize_entity(e) for e in fact["entities"]],
            ),
            "hrr_policy": (
                src.get("derived", {}).get("hrr_vector"),
                "rebuild" if fact["hrr_vector"] is not None else "absent",
            ),
        }
        for label, (actual, expected) in checks.items():
            checked_fields += 1
            if actual != expected:
                mismatches.append(
                    f"fact {fid} {label}: expected {expected!r}, got {actual!r}"
                )
        per_type[expected_type] += 1

    extra = sorted(set(docs) - {int(f["fact_id"]) for f in source})
    if extra:
        mismatches.append(f"extra OKF fact ids: {extra}")

    memanto: dict[str, Any] = {"checked": False}
    if memanto_repo is not None:
        sys.path.insert(0, str(memanto_repo.resolve()))
        try:
            from memanto.cli.migrate.mappers import map_okf
            from memanto.cli.migrate.okf_loader import load_okf_bundle

            loaded = load_okf_bundle(bundle)
            mapped = map_okf(loaded)
            bad_sources = [
                m.get("source")
                for m in mapped
                if m.get("source") != "hermes-holographic"
            ]
            missing_content = [
                f["fact_id"]
                for f in source
                if not any(
                    str(f["content"]) in str(m.get("content", "")) for m in mapped
                )
            ]
            memanto = {
                "checked": True,
                "loaded_entries": len(loaded.get("memories", [])),
                "mapped_memories": len(mapped),
                "source_preserved": not bad_sources,
                "all_fact_text_present": not missing_content,
            }
            if len(mapped) != len(source):
                mismatches.append(
                    f"Memanto mapper count: expected {len(source)}, got {len(mapped)}"
                )
            if bad_sources:
                mismatches.append(f"Memanto source field changed: {bad_sources}")
            if missing_content:
                mismatches.append(
                    f"Memanto mapped content missing facts: {missing_content}"
                )
        finally:
            sys.path.pop(0)

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "source_facts": len(source),
        "okf_memories": len(docs),
        "checked_fields": checked_fields,
        "per_type": dict(sorted(per_type.items())),
        "mismatches": mismatches,
        "memanto_loader_mapper": memanto,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--memanto-repo", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.db, args.bundle, args.memanto_repo)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

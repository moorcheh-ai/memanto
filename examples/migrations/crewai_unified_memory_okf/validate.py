#!/usr/bin/env python3
"""Validate source-to-OKF fidelity and deterministic golden recall parity."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from migrate import CrewAIRecord, canonical_sha256, read_lancedb_records

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "and",
    "are",
    "before",
    "by",
    "for",
    "from",
    "how",
    "is",
    "of",
    "the",
    "to",
    "what",
    "which",
    "who",
    "with",
}


def _tokens(text: str) -> Counter[str]:
    """Tokenize text for deterministic lexical recall scoring."""

    return Counter(
        token
        for token in TOKEN_RE.findall(text.lower())
        if token not in STOPWORDS and len(token) > 1
    )


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    """Compute cosine similarity between sparse token counters."""

    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _rank_rows(question: str, rows: list[dict[str, Any]]) -> list[str]:
    """Rank mapped rows by lexical similarity and stable tie-breakers."""

    query = _tokens(question)
    ranked = sorted(
        rows,
        key=lambda row: (
            _cosine(query, _tokens(f"{row['title']} {row['content']}")),
            float(row.get("confidence", 0.0)),
            str(row.get("source_ref") or ""),
        ),
        reverse=True,
    )
    return [str(row.get("source_ref") or "") for row in ranked]


def _record_from_entry(entry: dict[str, Any]) -> CrewAIRecord:
    """Reconstruct one CrewAI record from its OKF extension fields."""

    extra = entry.get("extra") or {}
    crewai = extra.get("crewai")
    if not isinstance(crewai, dict):
        raise ValueError(f"OKF entry {entry.get('source_path')} lacks crewai metadata")
    return CrewAIRecord(
        id=str(crewai["id"]),
        content=str(entry.get("body") or "").strip(),
        scope=str(crewai["scope"]),
        categories=tuple(str(item) for item in crewai.get("categories") or []),
        metadata=dict(crewai.get("metadata") or {}),
        importance=float(crewai["importance"]),
        created_at=str(entry["timestamp"]),
        last_accessed=str(crewai["last_accessed"]),
        source=str(crewai["source"]) if crewai.get("source") else None,
        private=bool(crewai.get("private", False)),
    )


def validate(
    source_database: Path,
    bundle: Path,
    source_evidence_path: Path,
    report_dir: Path,
) -> dict[str, Any]:
    """Validate exact reconstruction, mapping fidelity, and recall parity."""

    source_records = read_lancedb_records(source_database)
    source_by_id = {record.id: record for record in source_records}
    loaded = load_okf_bundle(bundle)
    entries = loaded.get("memories", [])
    mapped_rows = map_okf(loaded)

    reconstructed_by_id: dict[str, CrewAIRecord] = {}
    hash_checks: list[dict[str, Any]] = []
    mapping_checks: list[dict[str, Any]] = []
    mapped_by_uri = {
        str(row.get("source_ref")): row for row in mapped_rows if row.get("source_ref")
    }

    for entry in entries:
        reconstructed = _record_from_entry(entry)
        reconstructed_by_id[reconstructed.id] = reconstructed
        source = source_by_id.get(reconstructed.id)
        declared_hash = str((entry.get("extra") or {}).get("source_record_sha256"))
        source_hash = source.sha256 if source else None
        reconstructed_hash = reconstructed.sha256
        hash_checks.append(
            {
                "id": reconstructed.id,
                "source_sha256": source_hash,
                "declared_sha256": declared_hash,
                "reconstructed_sha256": reconstructed_hash,
                "exact": bool(
                    source_hash and source_hash == declared_hash == reconstructed_hash
                ),
            }
        )

        uri = f"crewai://unified-memory/{reconstructed.id}"
        row = mapped_by_uri.get(uri)
        expected_type = entry.get("x_memanto", {}).get("type")
        expected_tags = {str(tag) for tag in entry.get("tags") or []}
        mapping_checks.append(
            {
                "id": reconstructed.id,
                "mapped": row is not None,
                "type_preserved": bool(row and row.get("type") == expected_type),
                "confidence_preserved": bool(
                    row
                    and math.isclose(
                        float(row.get("confidence", -1)),
                        reconstructed.importance,
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                ),
                "tags_preserved": bool(
                    row and set(row.get("tags") or []) == expected_tags
                ),
                "resource_preserved": bool(row and row.get("source_ref") == uri),
            }
        )

    evidence = json.loads(source_evidence_path.read_text(encoding="utf-8"))
    recall_checks: list[dict[str, Any]] = []
    for query in evidence.get("golden_recall", []):
        expected_id = str(query["expected_id"])
        expected_uri = f"crewai://unified-memory/{expected_id}"
        after_ranking = _rank_rows(str(query["question"]), mapped_rows)
        try:
            after_rank = after_ranking.index(expected_uri) + 1
        except ValueError:
            after_rank = None
        before_rank = query.get("expected_rank")
        recall_checks.append(
            {
                "question": query["question"],
                "expected_id": expected_id,
                "crewai_rank": before_rank,
                "portable_okf_rank": after_rank,
                "crewai_top_3": bool(before_rank and before_rank <= 3),
                "portable_okf_top_3": bool(after_rank and after_rank <= 3),
                "parity": bool(
                    before_rank and before_rank <= 3 and after_rank and after_rank <= 3
                ),
            }
        )

    exact_count = sum(check["exact"] for check in hash_checks)
    mapped_count = sum(
        all(
            check[field]
            for field in (
                "mapped",
                "type_preserved",
                "confidence_preserved",
                "tags_preserved",
                "resource_preserved",
            )
        )
        for check in mapping_checks
    )
    parity_count = sum(check["parity"] for check in recall_checks)
    source_bundle_hash = canonical_sha256(
        [record.canonical_dict() for record in source_records]
    )
    reconstructed_bundle_hash = canonical_sha256(
        [
            reconstructed_by_id[record.id].canonical_dict()
            for record in source_records
            if record.id in reconstructed_by_id
        ]
    )

    report: dict[str, Any] = {
        "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_records": len(source_records),
        "okf_entries": len(entries),
        "memanto_mapped_rows": len(mapped_rows),
        "exact_record_hashes": exact_count,
        "mapping_checks_passed": mapped_count,
        "golden_recall_parity": f"{parity_count}/{len(recall_checks)}",
        "source_bundle_sha256": source_bundle_hash,
        "reconstructed_bundle_sha256": reconstructed_bundle_hash,
        "exact_bundle_match": source_bundle_hash == reconstructed_bundle_hash,
        "embedding_policy": (
            "Embedding vectors are intentionally excluded because they are derived, "
            "model-specific data; all semantic/provenance fields are exact."
        ),
        "hash_checks": hash_checks,
        "mapping_checks": mapping_checks,
        "recall_checks": recall_checks,
    }
    report["passed"] = bool(
        len(source_records)
        and len(source_records) == len(entries) == len(mapped_rows)
        and exact_count == len(source_records)
        and mapped_count == len(source_records)
        and parity_count == len(recall_checks)
        and report["exact_bundle_match"]
    )

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "round-trip-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown = [
        "# Round-trip validation report",
        "",
        f"- Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Source -> OKF exact record hashes: **{exact_count}/{len(source_records)}**",
        f"- OKF -> Memanto field mappings: **{mapped_count}/{len(source_records)}**",
        f"- Golden recall top-3 parity: **{parity_count}/{len(recall_checks)}**",
        f"- Whole-bundle canonical hash match: **{report['exact_bundle_match']}**",
        "- Embeddings: intentionally omitted derived data",
        "",
        "| Question | CrewAI rank | Portable OKF rank | Parity |",
        "|---|---:|---:|:---:|",
    ]
    markdown.extend(
        "| {question} | {crewai_rank} | {portable_okf_rank} | {status} |".format(
            question=str(check["question"]).replace("|", "\\|"),
            crewai_rank=check["crewai_rank"] or "-",
            portable_okf_rank=check["portable_okf_rank"] or "-",
            status="PASS" if check["parity"] else "FAIL",
        )
        for check in recall_checks
    )
    (report_dir / "ROUND_TRIP_REPORT.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8", newline="\n"
    )

    print(
        f"Validation {'PASS' if report['passed'] else 'FAIL'}: "
        f"{exact_count}/{len(source_records)} exact hashes, "
        f"{mapped_count}/{len(source_records)} Memanto mappings, "
        f"{parity_count}/{len(recall_checks)} recall parity"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the validation command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="CrewAI LanceDB directory")
    parser.add_argument("bundle", type=Path, help="Generated OKF bundle")
    parser.add_argument("source_evidence", type=Path, help="source-run.json")
    parser.add_argument("report_dir", type=Path, help="Validation report directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run validation and return a process status matching the report."""

    args = build_parser().parse_args(argv)
    report = validate(args.source, args.bundle, args.source_evidence, args.report_dir)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

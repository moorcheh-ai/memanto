"""Deterministic recall parity checks for the LangGraph -> OKF showcase."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from langgraph_checkpoint_to_okf import extract_records


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def read_okf_memories(okf_dir: Path) -> list[dict[str, Any]]:
    memories_dir = okf_dir / "memories"
    rows: list[dict[str, Any]] = []
    for path in sorted(memories_dir.rglob("*.md")):
        if path.name == "index.md":
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        _, raw_frontmatter, body = text.split("---", 2)
        data = yaml.safe_load(raw_frontmatter) or {}
        rows.append(
            {
                "title": data.get("title", ""),
                "type": data.get("type", ""),
                "content": body.strip(),
                "path": str(path.relative_to(okf_dir)),
            }
        )
    return rows


def contains_terms(rows: list[dict[str, Any]], terms: list[str]) -> tuple[bool, str]:
    normalized_terms = [
        f" {normalized} "
        for term in terms
        if (normalized := normalize(term))
    ]
    if not normalized_terms:
        return False, ""
    for row in rows:
        row_text = f"{row.get('title', '')} {row.get('content', '')}"
        haystack = f" {normalize(row_text)} "
        if all(term in haystack for term in normalized_terms):
            return True, row.get("title", "")
    return False, ""


def validate(
    source_db: Path,
    okf_dir: Path,
    golden_qa: Path,
    report_path: Path,
) -> dict[str, Any]:
    source_records = [
        {
            "title": record.title,
            "type": record.memory_type,
            "content": record.content,
        }
        for record in extract_records(source_db)
    ]
    okf_records = read_okf_memories(okf_dir)
    questions = json.loads(golden_qa.read_text(encoding="utf-8"))

    results = []
    for item in questions:
        source_ok, source_hit = contains_terms(source_records, item["expected_terms"])
        okf_ok, okf_hit = contains_terms(okf_records, item["expected_terms"])
        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "source_pass": source_ok,
                "okf_pass": okf_ok,
                "source_hit": source_hit,
                "okf_hit": okf_hit,
            }
        )

    source_score = sum(1 for row in results if row["source_pass"])
    okf_score = sum(1 for row in results if row["okf_pass"])
    parity_score = sum(
        1 for row in results if row["source_pass"] and row["okf_pass"]
    )

    summary = {
        "questions": len(questions),
        "source_score": source_score,
        "okf_score": okf_score,
        "parity_score": parity_score,
        "parity_percent": round((parity_score / len(questions)) * 100, 1),
        "results": results,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Recall Parity Report",
        "",
        "Deterministic golden Q&A validation over the source LangGraph checkpoint",
        "and the exported OKF bundle.",
        "",
        f"- Questions: {summary['questions']}",
        f"- Source checkpoint recall: {source_score}/{len(questions)}",
        f"- OKF recall: {okf_score}/{len(questions)}",
        f"- Source-to-OKF parity: {summary['parity_percent']}%",
        "",
        "| ID | Source | OKF | Matched OKF memory |",
        "| --- | --- | --- | --- |",
    ]
    for row in results:
        lines.append(
            "| {id} | {source} | {okf} | {hit} |".format(
                id=row["id"],
                source="pass" if row["source_pass"] else "fail",
                okf="pass" if row["okf_pass"] else "fail",
                hit=row["okf_hit"] or "-",
            )
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--okf-dir", type=Path, required=True)
    parser.add_argument(
        "--golden-qa", type=Path, default=Path("data/golden_qa.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("sample_output/validation/recall-parity-report.md")
    )
    args = parser.parse_args()

    summary = validate(args.source_db, args.okf_dir, args.golden_qa, args.report)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

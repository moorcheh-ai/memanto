"""Validate LangGraph checkpoint -> OKF -> Memanto mapping fidelity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from convert import extract_latest_memories, load_records

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

GOLDEN_QA = [
    {
        "question": "How should status updates be written for Robin?",
        "must_contain": ["concise", "three bullets"],
    },
    {
        "question": "What is the safest deploy window?",
        "must_contain": ["Tuesday mornings", "11:00 UTC"],
    },
    {
        "question": "What did Robin promise Nina?",
        "must_contain": ["onboarding bugfix", "Friday noon"],
    },
    {
        "question": "What is the OKF demo story decision?",
        "must_contain": ["open markdown memory bundles", "not a dashboard"],
    },
]


def _haystack(rows: list[dict[str, Any]]) -> str:
    return "\n".join(str(row.get("content") or "") for row in rows)


def validate(base_dir: Path) -> dict[str, Any]:
    records = load_records(base_dir / "data" / "source" / "langgraph_checkpoints.jsonl")
    source_memories = extract_latest_memories(records)
    okf_path = base_dir / "okf_bundle"
    entries = load_okf_bundle(okf_path)
    rows = map_okf(entries)
    text = _haystack(rows)

    missing = []
    for memory in source_memories:
        if str(memory["content"]) not in text:
            missing.append(memory["id"])

    qa_results = []
    for item in GOLDEN_QA:
        absent = [needle for needle in item["must_contain"] if needle not in text]
        qa_results.append(
            {
                "question": item["question"],
                "passed": not absent,
                "missing": absent,
            }
        )

    result = {
        "source_memories": len(source_memories),
        "okf_entries": len(entries["memories"]),
        "mapped_rows": len(rows),
        "missing_source_memory_ids": missing,
        "golden_qa": qa_results,
        "passed": (
            len(source_memories) == len(entries["memories"]) == len(rows)
            and not missing
            and all(row["passed"] for row in qa_results)
        ),
    }

    reports = base_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "roundtrip-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md = [
        "# Round-trip validation",
        "",
        f"- Source deduped memories: {result['source_memories']}",
        f"- OKF entries loaded: {result['okf_entries']}",
        f"- Memanto mapped rows: {result['mapped_rows']}",
        f"- Missing source ids: {result['missing_source_memory_ids'] or 'none'}",
        "",
        "| Golden question | Result | Missing snippets |",
        "| --- | --- | --- |",
    ]
    for row in qa_results:
        md.append(
            f"| {row['question']} | {'PASS' if row['passed'] else 'FAIL'} | "
            f"{', '.join(row['missing']) or '-'} |"
        )
    md.append("")
    (reports / "roundtrip-validation.md").write_text("\n".join(md), encoding="utf-8")
    if not result["passed"]:
        raise SystemExit("round-trip validation failed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    result = validate(args.base_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

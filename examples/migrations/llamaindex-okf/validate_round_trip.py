"""Validate source-to-OKF fidelity without an LLM or paid API."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from migrate_to_okf import _text_from_message, load_rows, redact_data

STOP_WORDS = {
    "a",
    "an",
    "and",
    "be",
    "does",
    "is",
    "not",
    "of",
    "the",
    "to",
    "what",
    "which",
    "who",
}


def _tokens(text: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        token = raw
        for suffix in ("ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) > len(suffix) + 3:
                token = token[: -len(suffix)]
                break
        if token not in STOP_WORDS:
            tokens.add(token)
    return tokens


def retrieve_answer(question: str, records: list[str], expected: str) -> dict:
    """Retrieve the best record by deterministic query-token overlap."""
    query = _tokens(question)
    ranked = sorted(
        (
            (len(query & _tokens(record)), index, record)
            for index, record in enumerate(records)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    score, _, retrieved = ranked[0] if ranked else (0, -1, "")
    passed = score > 0 and expected.lower() in retrieved.lower()
    return {
        "question": question,
        "expected": expected,
        "retrieved": retrieved or None,
        "overlap_score": score,
        "passed": passed,
    }


def okf_records(bundle: Path) -> dict[int, dict]:
    records = {}
    for path in sorted((bundle / "memories").glob("*/*.md")):
        raw = path.read_text(encoding="utf-8")
        _, front, body = raw.split("---", 2)
        metadata = yaml.safe_load(front)
        records[int(metadata["x_llamaindex"]["message_id"])] = {
            "metadata": metadata,
            "text": body.strip(),
        }
    return records


def validate(database: Path, bundle: Path, golden_path: Path) -> dict:
    source_rows = load_rows(database)
    migrated = okf_records(bundle)
    failures = []
    for order, row in enumerate(source_rows, 1):
        source_data = json.loads(row["data"])
        source_text = _text_from_message(source_data)
        target = migrated.get(int(row["id"]))
        if target is None:
            failures.append(f"source row {row['id']} missing")
            continue
        extension = target["metadata"]["x_llamaindex"]
        checks = {
            "text": target["text"] == source_text,
            "session": extension["session_id"] == row["key"],
            "role": extension["role"] == row["role"],
            "status": extension["status"] == row["status"],
            "order": extension["order"] == order,
            "additional_kwargs": extension["additional_kwargs"]
            == redact_data(source_data.get("additional_kwargs", {})),
        }
        failures.extend(
            f"source row {row['id']} failed {name} parity"
            for name, passed in checks.items()
            if not passed
        )

    migrated_texts = [record["text"] for record in migrated.values()]
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    qa_results = [
        retrieve_answer(case["question"], migrated_texts, case["expected"])
        for case in golden
    ]
    failures.extend(
        f"golden recall failed: {item['question']}"
        for item in qa_results
        if not item["passed"]
    )
    total = len(source_rows)
    report = {
        "source_records": total,
        "okf_records": len(migrated),
        "record_recall": len(migrated) / total if total else 1.0,
        "field_parity_checks": total * 6,
        "golden_questions": len(qa_results),
        "golden_recall": (
            sum(item["passed"] for item in qa_results) / len(qa_results)
            if qa_results
            else 1.0
        ),
        "passed": not failures,
        "failures": failures,
        "qa_results": qa_results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--golden", type=Path, default=Path(__file__).with_name("golden_qa.json")
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.database, args.bundle, args.golden)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Compare identical source and Memanto question sets without inventing answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_parity(source_path: Path, memanto_path: Path) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    memanto = json.loads(memanto_path.read_text(encoding="utf-8"))
    source_results = source["results"]
    memanto_results = memanto["results"]
    if len(source_results) != len(memanto_results):
        raise ValueError("Source and Memanto reports have different question counts")

    results: list[dict[str, Any]] = []
    for before, after in zip(source_results, memanto_results, strict=True):
        if before["question"] != after["question"]:
            raise ValueError("Source and Memanto reports do not ask identical questions")
        passed = bool(before["passed"] and after["passed"])
        results.append(
            {
                "question": before["question"],
                "source_answer": before["answer"],
                "memanto_answer": after["answer"],
                "source_passed": bool(before["passed"]),
                "memanto_passed": bool(after["passed"]),
                "parity_passed": passed,
            }
        )
    passed = sum(result["parity_passed"] for result in results)
    return {
        "questions": len(results),
        "passed": passed,
        "recall_parity": passed / len(results) if results else 1.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("memanto", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_parity(args.source, args.memanto)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["recall_parity"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

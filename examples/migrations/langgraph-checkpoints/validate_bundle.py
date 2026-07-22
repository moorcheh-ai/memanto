"""Validate recall parity between the source scenario and an OKF bundle."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def load_documents(bundle: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted((bundle / "memories").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            raise ValueError(f"Missing YAML frontmatter: {path}")
        frontmatter = yaml.safe_load(match.group(1)) or {}
        if not isinstance(frontmatter, dict):
            raise ValueError(f"Invalid YAML frontmatter: {path}")
        documents.append(
            {"path": str(path), "frontmatter": frontmatter, "body": match.group(2)}
        )
    return documents


def validate_recall(bundle: Path, golden_file: Path) -> dict[str, Any]:
    documents = load_documents(bundle)
    corpus = "\n".join(document["body"] for document in documents).casefold()
    cases = json.loads(golden_file.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in cases:
        expected = [str(value).casefold() for value in case["expected_terms"]]
        matched = all(value in corpus for value in expected)
        results.append(
            {
                "question": case["question"],
                "expected_terms": case["expected_terms"],
                "passed": matched,
            }
        )
    passed = sum(1 for result in results if result["passed"])
    return {
        "questions": len(results),
        "passed": passed,
        "recall_parity": passed / len(results) if results else 1.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("golden", type=Path, nargs="?", default=Path("golden_qa.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate_recall(args.bundle, args.golden)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report["recall_parity"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

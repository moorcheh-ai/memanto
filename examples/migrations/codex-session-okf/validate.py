#!/usr/bin/env python3
"""Validate source-to-OKF recall parity with a small golden Q&A set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    """Compare source and exported OKF recall against golden expectations."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("okf", type=Path)
    parser.add_argument("golden", type=Path)
    args = parser.parse_args()

    source_text = args.source.read_text(encoding="utf-8")
    okf_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((args.okf / "memories").rglob("*.md"))
        if path.name != "index.md"
    )
    questions = json.loads(args.golden.read_text(encoding="utf-8"))

    results = []
    for item in questions:
        expected = item["expected"]
        source_hit = all(term in source_text for term in expected)
        okf_hit = all(term in okf_text for term in expected)
        results.append(
            {
                "question": item["question"],
                "expected_terms": expected,
                "source_recall": source_hit,
                "okf_recall": okf_hit,
                "parity": source_hit == okf_hit,
            }
        )

    passed = sum(item["source_recall"] and item["okf_recall"] for item in results)
    report = {
        "questions": len(results),
        "source_recalled": sum(item["source_recall"] for item in results),
        "okf_recalled": sum(item["okf_recall"] for item in results),
        "exact_recall_parity": sum(item["parity"] for item in results),
        "passed": passed,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compare golden recall against a Codex source export and an OKF bundle."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "be",
    "before",
    "for",
    "how",
    "is",
    "must",
    "should",
    "the",
    "to",
    "what",
    "which",
}


@dataclass(frozen=True)
class RecallResult:
    question_id: str
    question: str
    passed: bool
    expected_all: list[str]
    missing: list[str]
    evidence: str


def _normalized(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOP_WORDS and len(token) > 1
    }


def load_golden(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array")
    for item in payload:
        if not isinstance(item, dict) or not item.get("expected_all"):
            raise ValueError(f"{path} contains an invalid golden question")
    return payload


def load_source_documents(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"{path} has no Codex source records")
    return [
        "\n".join(
            (
                str(record.get("raw_memory") or ""),
                str(record.get("rollout_summary") or ""),
            )
        )
        for record in records
        if isinstance(record, dict)
    ]


def load_okf_documents(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"OKF bundle not found: {path}")
    if path.is_file():
        files = [path]
    else:
        memories_dir = path / "memories"
        scan_root = memories_dir if memories_dir.is_dir() else path
        files = sorted(scan_root.rglob("*.md"))
    return [
        file_path.read_text(encoding="utf-8")
        for file_path in files
        if file_path.name.lower() not in {"index.md", "log.md"}
    ]


def retrieve(question: str, documents: list[str]) -> str:
    if not documents:
        return ""
    query_tokens = _tokens(question)
    return max(
        documents,
        key=lambda document: (
            len(query_tokens & _tokens(document)),
            len(document),
        ),
    )


def _evidence(document: str, expected: list[str], radius: int = 90) -> str:
    normalized_document = document.replace("\n", " ")
    lower_document = normalized_document.lower()
    positions = [
        lower_document.find(term.lower())
        for term in expected
        if lower_document.find(term.lower()) >= 0
    ]
    if not positions:
        return normalized_document[: radius * 2].strip()
    start = max(min(positions) - radius, 0)
    end = min(max(positions) + max(map(len, expected)) + radius, len(document))
    return re.sub(r"\s+", " ", normalized_document[start:end]).strip()


def evaluate(golden: list[dict[str, Any]], documents: list[str]) -> list[RecallResult]:
    results = []
    for item in golden:
        expected = [str(term) for term in item["expected_all"]]
        document = retrieve(str(item["question"]), documents)
        normalized_document = _normalized(document)
        missing = [
            term for term in expected if _normalized(term) not in normalized_document
        ]
        results.append(
            RecallResult(
                question_id=str(item["id"]),
                question=str(item["question"]),
                passed=not missing,
                expected_all=expected,
                missing=missing,
                evidence=_evidence(document, expected),
            )
        )
    return results


def _score(results: list[RecallResult]) -> float:
    if not results:
        return 0.0
    return round(100 * sum(result.passed for result in results) / len(results), 1)


def build_parser() -> argparse.ArgumentParser:
    example_dir = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(
        description="Score source-to-OKF golden recall parity."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).with_name("golden_qa.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=example_dir / "out" / "recall_report.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    golden = load_golden(args.golden)
    source_results = evaluate(golden, load_source_documents(args.source))
    bundle_results = evaluate(golden, load_okf_documents(args.bundle))
    source_score = _score(source_results)
    bundle_score = _score(bundle_results)
    report = {
        "schema": "codex-okf-recall-parity/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": len(golden),
        "source_score": source_score,
        "okf_score": bundle_score,
        "parity_delta": round(bundle_score - source_score, 1),
        "source_results": [asdict(result) for result in source_results],
        "okf_results": [asdict(result) for result in bundle_results],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Golden recall parity")
    print(f"  Source: {source_score:.1f}%")
    print(f"  OKF:    {bundle_score:.1f}%")
    print(f"  Delta:  {bundle_score - source_score:+.1f} points")
    print(f"  Report: {args.report}")
    return 0 if source_score == 100.0 and bundle_score == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

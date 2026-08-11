#!/usr/bin/env python3
"""Validate OKF importability, reconstruction, privacy, and recall parity."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from adapter import load_history, render_message, scan_history
from reconstruct import reconstruct

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "and",
    "for",
    "in",
    "is",
    "of",
    "the",
    "to",
    "what",
    "which",
}


def _tokens(value: str) -> set[str]:
    # Preserve useful word boundaries in identifiers such as PydanticAI and in
    # package/path names such as pydantic-ai-slim.  This is intentionally a
    # small, dependency-free lexical baseline rather than a semantic model.
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return {
        token for token in _TOKEN_RE.findall(expanded.casefold()) if token not in _STOP
    }


def _retrieve(query: str, documents: list[str], limit: int = 4) -> list[int]:
    query_tokens = _tokens(query)
    scored: list[tuple[float, int]] = []
    for index, document in enumerate(documents):
        document_tokens = _tokens(document)
        overlap = len(query_tokens & document_tokens)
        score = overlap / max(1, len(query_tokens))
        scored.append((score, index))
    return [
        index
        for score, index in sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
        if score > 0
    ]


def _contains_expected(text: str, expected: list[str]) -> bool:
    folded = text.casefold()
    return all(item.casefold() in folded for item in expected)


def validate(
    source: Path,
    bundle: Path,
    questions_path: Path,
) -> dict[str, Any]:
    history = load_history(source)
    reconstructed, reconstruction = reconstruct(bundle)
    if reconstructed != list(history.messages):
        raise ValueError("reconstructed messages differ from the source history")

    try:
        from memanto.cli.migrate.mappers import map_okf, type_breakdown
        from memanto.cli.migrate.okf_loader import load_okf_bundle
    except ImportError as exc:  # pragma: no cover - user-facing environment error
        raise RuntimeError(
            "install Memanto from the repository before validating"
        ) from exc

    export = load_okf_bundle(bundle)
    rows = map_okf(export)
    if len(rows) != len(history.messages):
        raise ValueError(
            f"Memanto mapped {len(rows)} rows for {len(history.messages)} messages"
        )

    source_docs = [
        render_message(message, index).body
        for index, message in enumerate(history.messages)
    ]
    okf_docs = [str(row.get("content") or "") for row in rows]
    questions = json.loads(questions_path.read_text("utf-8"))
    results: list[dict[str, Any]] = []
    source_hits = 0
    okf_hits = 0
    selected_source_bytes = 0
    selected_okf_bytes = 0

    for item in questions:
        query = str(item["question"])
        expected = [str(value) for value in item["expected_substrings"]]
        source_indexes = _retrieve(query, source_docs)
        okf_indexes = _retrieve(query, okf_docs)
        source_context = "\n".join(source_docs[index] for index in source_indexes)
        okf_context = "\n".join(okf_docs[index] for index in okf_indexes)
        source_pass = _contains_expected(source_context, expected)
        okf_pass = _contains_expected(okf_context, expected)
        source_hits += int(source_pass)
        okf_hits += int(okf_pass)
        selected_source_bytes += len(source_context.encode("utf-8"))
        selected_okf_bytes += len(okf_context.encode("utf-8"))
        results.append(
            {
                "id": item["id"],
                "question": query,
                "expected_substrings": expected,
                "source_top_indexes": source_indexes,
                "okf_top_indexes": okf_indexes,
                "source_pass": source_pass,
                "okf_pass": okf_pass,
            }
        )

    total = len(questions)
    source_full_bytes = sum(len(document.encode("utf-8")) for document in source_docs)
    okf_full_bytes = sum(len(document.encode("utf-8")) for document in okf_docs)
    source_full_across_queries = source_full_bytes * total
    okf_full_across_queries = okf_full_bytes * total
    findings = scan_history(history.messages)
    recall_parity = source_hits == okf_hits == total
    privacy_pass = not findings
    report = {
        "source_messages": len(history.messages),
        "okf_nodes": len(export["memories"]),
        "memanto_mapped": len(rows),
        "memanto_skipped": len(export["memories"]) - len(rows),
        "type_breakdown": type_breakdown(rows),
        "reconstruction": reconstruction,
        "privacy": {
            "finding_count": len(findings),
            "categories": dict(Counter(finding.category for finding in findings)),
            "pass": privacy_pass,
        },
        "recall": {
            "questions": total,
            "source_passed": source_hits,
            "okf_passed": okf_hits,
            "source_score": source_hits / total if total else 0,
            "okf_score": okf_hits / total if total else 0,
            "parity": recall_parity,
            "method": "deterministic lexical top-4 retrieval with exact golden substrings",
            "results": results,
        },
        "savings": {
            "honesty_note": (
                "These are measured UTF-8 context bytes, not invented token, cost, "
                "or network-latency claims. Live Moorcheh metrics require a real key."
            ),
            "measurement_basis": (
                "Selected bytes summed across all recall queries versus sending the "
                "complete context separately for every query."
            ),
            "recall_queries": total,
            "source_full_context_bytes_per_query": source_full_bytes,
            "okf_full_context_bytes_per_query": okf_full_bytes,
            "source_full_context_bytes_across_queries": source_full_across_queries,
            "okf_full_context_bytes_across_queries": okf_full_across_queries,
            "source_selected_context_bytes_across_queries": selected_source_bytes,
            "okf_selected_context_bytes_across_queries": selected_okf_bytes,
            "okf_retrieval_reduction_percent": round(
                (1 - selected_okf_bytes / max(1, okf_full_across_queries)) * 100,
                2,
            ),
        },
    }
    if not recall_parity:
        failed = ", ".join(
            item["id"]
            for item in results
            if not item["source_pass"] or not item["okf_pass"]
        )
        raise ValueError(f"golden recall parity failed: {failed}")
    if not privacy_pass:
        raise ValueError("privacy scan failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.source, args.bundle, args.questions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Messages        : {report['source_messages']}")
    print(f"Memanto mapped  : {report['memanto_mapped']}")
    print(
        "Recall parity   : "
        f"{report['recall']['source_passed']}/{report['recall']['questions']} -> "
        f"{report['recall']['okf_passed']}/{report['recall']['questions']}"
    )
    print(f"Privacy findings: {report['privacy']['finding_count']}")
    print(f"Report          : {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

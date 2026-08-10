#!/usr/bin/env python3
"""Validate OKF structure and deterministic golden-question recall parity."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
WORD_RE = re.compile(r"[\w$]+", re.UNICODE)


@dataclass(frozen=True)
class Document:
    path: str
    metadata: dict[str, Any]
    body: str


def load_documents(bundle: Path) -> list[Document]:
    documents: list[Document] = []
    for path in sorted((bundle / "memories").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            raise ValueError(f"Missing YAML frontmatter: {path}")
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"Frontmatter is not a mapping: {path}")
        documents.append(
            Document(
                path=path.relative_to(bundle).as_posix(),
                metadata=metadata,
                body=match.group(2).strip(),
            )
        )
    return documents


def tokens(text: str) -> set[str]:
    return {token.casefold() for token in WORD_RE.findall(text) if len(token) > 2}


def retrieve(query: str, documents: list[Document]) -> Document:
    query_tokens = tokens(query)

    token_sets = [
        tokens(document.body + " " + str(document.metadata.get("title", "")))
        for document in documents
    ]
    document_frequency = {
        token: sum(token in document_tokens for document_tokens in token_sets)
        for token in query_tokens
    }

    def score(item: tuple[Document, set[str]]) -> tuple[float, int, str]:
        document, body_tokens = item
        relevance = sum(
            math.log((len(documents) + 1) / (document_frequency[token] + 1)) + 1
            for token in query_tokens & body_tokens
        )
        tags = document.metadata.get("tags") or []
        # User-authored constraints/goals are the primary source of truth when
        # an assistant status update repeats the same terms.
        if "role:user" in tags:
            relevance += 0.75
        return relevance, -len(document.body), document.path

    return max(zip(documents, token_sets, strict=True), key=score)[0]


def validate(bundle: Path, golden_path: Path) -> dict[str, Any]:
    documents = load_documents(bundle)
    if not documents:
        raise ValueError("Bundle contains no memory documents")

    resources: set[str] = set()
    structural_errors: list[str] = []
    for document in documents:
        metadata = document.metadata
        for field in ("type", "title", "resource", "timestamp", "x_memanto"):
            if not metadata.get(field):
                structural_errors.append(f"{document.path}: missing {field}")
        resource = str(metadata.get("resource") or "")
        if resource in resources:
            structural_errors.append(f"{document.path}: duplicate resource {resource}")
        resources.add(resource)
        x_memanto = metadata.get("x_memanto") or {}
        if x_memanto.get("source") != "codex":
            structural_errors.append(f"{document.path}: source is not codex")

    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    passed = 0
    for case in golden:
        document = retrieve(str(case["question"]), documents)
        haystack = re.sub(
            r"\s+",
            " ",
            document.body + " " + str(document.metadata.get("title", "")),
        ).casefold()
        expected_terms = [
            re.sub(r"\s+", " ", str(term)).casefold() for term in case["expected_terms"]
        ]
        terms_ok = all(term in haystack for term in expected_terms)
        type_ok = document.metadata.get("type") == case["expected_type"]
        ok = terms_ok and type_ok
        passed += int(ok)
        cases.append(
            {
                "question": case["question"],
                "retrieved": document.path,
                "expected_type": case["expected_type"],
                "actual_type": document.metadata.get("type"),
                "expected_terms": case["expected_terms"],
                "passed": ok,
            }
        )

    result = {
        # Keep committed reports reproducible and free of local filesystem paths.
        "bundle": bundle.name,
        "documents": len(documents),
        "structural_errors": structural_errors,
        "golden_questions": len(cases),
        "golden_passed": passed,
        "recall_parity_percent": round(100 * passed / len(cases), 1) if cases else 0,
        "cases": cases,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    result = validate(args.bundle, args.golden)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return (
        0
        if not result["structural_errors"]
        and result["golden_passed"] == result["golden_questions"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

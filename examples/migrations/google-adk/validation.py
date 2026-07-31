#!/usr/bin/env python3
"""Golden-question recall validation for source state and migrated OKF."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from scenario import GOLDEN_QUESTIONS

STOPWORDS = {
    "a",
    "and",
    "be",
    "current",
    "did",
    "do",
    "for",
    "how",
    "is",
    "of",
    "should",
    "the",
    "to",
    "what",
    "when",
    "who",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def source_documents(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Build a search corpus directly from current ADK state tables."""
    documents = []
    for scope, section in (
        ("app", "app_states"),
        ("user", "user_states"),
        ("session", "sessions"),
    ):
        for row in snapshot.get(section, []):
            for key, value in (row.get("state") or {}).items():
                content = (
                    value
                    if isinstance(value, str)
                    else json.dumps(value, ensure_ascii=False, sort_keys=True)
                )
                documents.append(
                    {
                        "id": f"{scope}:{row['app_name']}:{key}",
                        "title": str(key),
                        "content": str(content),
                    }
                )
    return documents


def okf_documents(bundle: str | Path) -> list[dict[str, str]]:
    """Load the bundle through Memanto's shipped OKF loader and mapper."""
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    rows = map_okf(load_okf_bundle(bundle))
    return [
        {
            "id": str(row.get("source_ref") or index),
            "title": str(row.get("title") or ""),
            "content": str(row.get("content") or ""),
        }
        for index, row in enumerate(rows)
    ]


def _rank(query: str, documents: Iterable[dict[str, str]], limit: int = 3):
    query_tokens = _tokens(query)
    ranked = []
    for document in documents:
        title_tokens = _tokens(document["title"])
        body_tokens = _tokens(document["content"])
        exact_title = len(query_tokens & title_tokens)
        exact_body = len(query_tokens & body_tokens)
        substring = sum(
            1 for token in query_tokens if token in document["content"].casefold()
        )
        score = exact_title * 4 + exact_body * 2 + substring
        ranked.append((score, document["id"], document))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _score_answer(
    answer: str, expected_groups: Iterable[Iterable[str]]
) -> dict[str, Any]:
    folded = answer.casefold()
    groups = [tuple(group) for group in expected_groups]
    matched = [any(alias.casefold() in folded for alias in group) for group in groups]
    score = sum(matched) / len(groups) if groups else 1.0
    return {"score": score, "matched_groups": matched, "total_groups": len(groups)}


def validate_documents(
    documents: list[dict[str, str]], *, corpus_name: str
) -> dict[str, Any]:
    results = []
    for question in GOLDEN_QUESTIONS:
        hits = _rank(question["question"], documents)
        answer = "\n\n".join(f"{hit['title']}\n{hit['content']}" for hit in hits)
        score = _score_answer(answer, question["expected_groups"])
        results.append(
            {
                "id": question["id"],
                "question": question["question"],
                **score,
                "top_document_ids": [hit["id"] for hit in hits],
                "answer_excerpt": answer[:600],
            }
        )
    average = sum(item["score"] for item in results) / len(results)
    return {
        "schema": "google-adk-golden-validation/v1",
        "corpus": corpus_name,
        "documents": len(documents),
        "questions": len(results),
        "passed": sum(item["score"] == 1.0 for item in results),
        "average_score": round(average, 4),
        "score_distribution": dict(
            sorted(Counter(str(item["score"]) for item in results).items())
        ),
        "method": (
            "Deterministic lexical retrieval over current durable state; each "
            "question scores the fraction of required answer groups found."
        ),
        "results": results,
    }


def compare_reports(source: dict[str, Any], migrated: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["id"]: item for item in migrated["results"]}
    parity = []
    for item in source["results"]:
        after = by_id[item["id"]]
        parity.append(
            {
                "id": item["id"],
                "source_score": item["score"],
                "okf_score": after["score"],
                "delta": round(after["score"] - item["score"], 4),
            }
        )
    return {
        "schema": "google-adk-recall-parity/v1",
        "questions": len(parity),
        "source_average": source["average_score"],
        "okf_average": migrated["average_score"],
        "average_delta": round(migrated["average_score"] - source["average_score"], 4),
        "zero_amnesia": all(item["delta"] >= 0 for item in parity),
        "results": parity,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

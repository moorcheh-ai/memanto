"""Deterministic golden-set scoring for migration recall evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

try:
    from examples.migrations.hindsight.scenario import GOLDEN_QUESTIONS
except ModuleNotFoundError:
    from scenario import GOLDEN_QUESTIONS

RECALL_RESULT_LIMIT = 10


def normalize_text(value: str) -> str:
    """Normalize an answer for case-insensitive phrase matching."""
    return re.sub(r"\s+", " ", value).strip().casefold()


def score_answer(answer: str, expected_groups: Iterable[Iterable[str]]) -> float:
    """Score the fraction of required synonym groups present in an answer."""
    normalized = normalize_text(answer)
    groups = [tuple(group) for group in expected_groups]
    if not groups:
        return 1.0
    hits = sum(
        any(normalize_text(term) in normalized for term in group) for group in groups
    )
    return round(hits / len(groups), 4)


def evaluate_retriever(
    name: str,
    retriever: Callable[[str], tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """Run the shared golden set against a source or destination retriever."""
    cases = []
    for question in GOLDEN_QUESTIONS:
        answer, evidence = retriever(question["question"])
        score = score_answer(answer, question["expected_groups"])
        cases.append(
            {
                "id": question["id"],
                "question": question["question"],
                "expected_groups": question["expected_groups"],
                "answer": answer,
                "evidence": evidence,
                "score": score,
                "passed": score == 1.0,
            }
        )
    average = sum(case["score"] for case in cases) / len(cases)
    return {
        "retriever": name,
        "questions": len(cases),
        "passed": sum(case["passed"] for case in cases),
        "average_score": round(average, 4),
        "cases": cases,
    }


def rescore_report(report: dict[str, Any]) -> dict[str, Any]:
    """Reapply the current golden rubric to already captured source answers."""
    rubric = {question["id"]: question for question in GOLDEN_QUESTIONS}
    cases = []
    for existing in report["cases"]:
        question = rubric[existing["id"]]
        score = score_answer(existing["answer"], question["expected_groups"])
        cases.append(
            {
                **existing,
                "question": question["question"],
                "expected_groups": question["expected_groups"],
                "score": score,
                "passed": score == 1.0,
            }
        )
    average = sum(case["score"] for case in cases) / len(cases)
    return {
        **report,
        "questions": len(cases),
        "passed": sum(case["passed"] for case in cases),
        "average_score": round(average, 4),
        "cases": cases,
    }


def hindsight_retriever(
    client: Any,
    bank_id: str,
    *,
    limit: int = RECALL_RESULT_LIMIT,
):
    """Create a retriever backed by Hindsight's real recall operation."""

    def retrieve(question: str) -> tuple[str, list[dict[str, Any]]]:
        response = client.recall(
            bank_id=bank_id,
            query=question,
            budget="high",
            max_tokens=4096,
            include_source_facts=True,
        )
        results = [
            result.to_dict() if hasattr(result, "to_dict") else dict(result)
            for result in response.results
        ][:limit]
        answer = "\n".join(str(result.get("text") or "") for result in results)
        return answer, results

    return retrieve


def memanto_retriever(
    client: Any,
    agent_id: str,
    *,
    limit: int = RECALL_RESULT_LIMIT,
):
    """Create a retriever backed by Memanto's real semantic recall operation."""

    def retrieve(question: str) -> tuple[str, list[dict[str, Any]]]:
        response = client.recall(
            agent_id=agent_id,
            query=question,
            limit=limit,
            min_similarity=0.0,
        )
        memories = response.get("memories", [])
        evidence = [
            {
                key: memory[key]
                for key in (
                    "id",
                    "title",
                    "content",
                    "type",
                    "tags",
                    "score",
                    "confidence",
                    "computed_confidence",
                )
                if key in memory
            }
            for memory in memories
            if isinstance(memory, dict)
        ]
        answer = "\n".join(
            "\n".join(
                str(memory.get(key) or "")
                for key in ("title", "content")
                if memory.get(key)
            )
            for memory in evidence
        )
        return answer, evidence

    return retrieve


def build_parity_report(
    source: dict[str, Any],
    destination: dict[str, Any],
) -> dict[str, Any]:
    """Compare shared golden-set scores without hiding partial regressions."""
    source_cases = {case["id"]: case for case in source["cases"]}
    destination_cases = {case["id"]: case for case in destination["cases"]}
    if source_cases.keys() != destination_cases.keys():
        raise ValueError("Source and destination reports use different case IDs")

    cases = []
    for case_id, source_case in source_cases.items():
        destination_case = destination_cases[case_id]
        cases.append(
            {
                "id": case_id,
                "source_score": source_case["score"],
                "destination_score": destination_case["score"],
                "delta": round(
                    destination_case["score"] - source_case["score"],
                    4,
                ),
                "retained_or_improved": (
                    destination_case["score"] >= source_case["score"]
                ),
            }
        )

    source_average = float(source["average_score"])
    destination_average = float(destination["average_score"])
    score_retention = destination_average / source_average if source_average else 1.0
    return {
        "schema": "hindsight-memanto-recall-parity/v1",
        "questions": len(cases),
        "source": {
            "retriever": source["retriever"],
            "passed": source["passed"],
            "average_score": source_average,
        },
        "destination": {
            "retriever": destination["retriever"],
            "passed": destination["passed"],
            "average_score": destination_average,
        },
        "retained_or_improved": sum(case["retained_or_improved"] for case in cases),
        "mean_score_retention": round(score_retention, 4),
        "cases": cases,
    }


def write_report(
    report: dict[str, Any],
    output: Path,
    *,
    prefix: str = "source-recall",
    title: str = "Hindsight source recall — golden validation set",
    note: str = (
        "Scores are deterministic phrase-group coverage over Hindsight's "
        "retrieved source memories, not an LLM self-grade."
    ),
) -> None:
    """Write machine-readable and human-readable validation artifacts."""
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{prefix}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# {title}",
        "",
        f"- Questions: {report['questions']}",
        f"- Full passes: {report['passed']}/{report['questions']}",
        f"- Mean required-fact coverage: {report['average_score']:.1%}",
        "",
        "| Case | Score | Result |",
        "|---|---:|---|",
    ]
    for case in report["cases"]:
        result = "pass" if case["passed"] else "partial"
        lines.append(f"| {case['id']} | {case['score']:.0%} | {result} |")
    lines.extend(
        [
            "",
            f"> {note}",
            "",
        ]
    )
    (output / f"{prefix}.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_parity_report(report: dict[str, Any], output: Path) -> None:
    """Write the source-to-destination recall comparison."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "recall-parity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Hindsight → Memanto recall parity",
        "",
        (f"- Source full passes: {report['source']['passed']}/{report['questions']}"),
        (
            f"- Destination full passes: {report['destination']['passed']}/"
            f"{report['questions']}"
        ),
        f"- Mean score retention: {report['mean_score_retention']:.1%}",
        (
            f"- Cases retained or improved: {report['retained_or_improved']}/"
            f"{report['questions']}"
        ),
        "",
        "| Case | Hindsight | Memanto | Delta |",
        "|---|---:|---:|---:|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['id']} | {case['source_score']:.0%} | "
            f"{case['destination_score']:.0%} | {case['delta']:+.0%} |"
        )
    lines.extend(
        [
            "",
            (
                "> Both sides use the same questions and explicit required-phrase "
                "groups. The destination answer is the concatenated raw Memanto "
                "recall result, not a generated answer."
            ),
            "",
        ]
    )
    (output / "recall-parity.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

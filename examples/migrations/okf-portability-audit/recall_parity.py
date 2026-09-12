"""Verify golden-question recall before and after an OKF round trip."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from okf_audit import validate_report_output, write_report

from memanto.cli.migrate.okf_loader import load_okf_bundle

_TOKEN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "is",
    "of",
    "the",
    "to",
    "what",
    "when",
    "which",
}


def _tokens(text: Any, *, drop_stopwords: bool = False) -> list[str]:
    """Return stable case-folded word and number tokens."""
    tokens = [token.casefold() for token in _TOKEN.findall(str(text or ""))]
    if drop_stopwords:
        return [token for token in tokens if token not in _STOPWORDS]
    return tokens


def _field_text(entry: dict[str, Any], field: str) -> str:
    """Render a searchable scalar or list OKF field."""
    value = entry.get(field)
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _rank(
    entries: list[dict[str, Any]], question: str, top_k: int
) -> list[tuple[int, dict[str, Any]]]:
    """Rank memories with a small deterministic lexical retriever."""
    query = set(_tokens(question, drop_stopwords=True))
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for entry in entries:
        title = Counter(_tokens(_field_text(entry, "title")))
        description = Counter(_tokens(_field_text(entry, "description")))
        tags = Counter(_tokens(_field_text(entry, "tags")))
        body = Counter(_tokens(_field_text(entry, "body")))
        score = sum(
            5 * min(title[token], 1)
            + 3 * min(description[token], 1)
            + 2 * min(tags[token], 1)
            + min(body[token], 3)
            for token in query
        )
        if score:
            source_path = str(entry.get("source_path") or "")
            ranked.append((score, source_path, entry))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(score, entry) for score, _, entry in ranked[:top_k]]


def _contains_token_sequence(tokens: list[str], phrase: list[str]) -> bool:
    """Return whether a contiguous, ordered token phrase is present."""
    return any(
        tokens[index : index + len(phrase)] == phrase
        for index in range(len(tokens) - len(phrase) + 1)
    )


def _contains_answer(entry: dict[str, Any], accepted_answers: list[str]) -> bool:
    """Match an accepted answer without using it to rank the documents."""
    return any(
        bool(answer_tokens := _tokens(answer))
        and any(
            _contains_token_sequence(_tokens(_field_text(entry, field)), answer_tokens)
            for field in ("title", "description", "tags", "body", "resource")
        )
        for answer in accepted_answers
    )


def _load_questions(path: Path) -> list[dict[str, Any]]:
    """Load and validate the explicit golden-question set."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Golden-question file must contain a non-empty list")
    questions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each golden question must be an object")
        question_id = str(item.get("id") or "").strip()
        question = str(item.get("question") or "").strip()
        accepted = item.get("accepted_answers")
        if not question_id or not question or not isinstance(accepted, list):
            raise ValueError("Each question needs id, question, and accepted_answers")
        answers = [str(answer).strip() for answer in accepted if str(answer).strip()]
        if not answers:
            raise ValueError(f"Question {question_id!r} has no accepted answer")
        questions.append(
            {"id": question_id, "question": question, "accepted_answers": answers}
        )
    if len({item["id"] for item in questions}) != len(questions):
        raise ValueError("Golden-question IDs must be unique")
    return questions


def _evaluate(
    entries: list[dict[str, Any]], questions: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """Evaluate one bundle and keep compact retrieval evidence."""
    results: list[dict[str, Any]] = []
    for item in questions:
        ranked = _rank(entries, item["question"], top_k)
        matched = next(
            (
                entry
                for _, entry in ranked
                if _contains_answer(entry, item["accepted_answers"])
            ),
            None,
        )
        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "accepted_answers": item["accepted_answers"],
                "hit": matched is not None,
                "matched_record": (
                    str(matched.get("source_path") or matched.get("title") or "")
                    if matched
                    else None
                ),
                "top_records": [
                    {
                        "score": score,
                        "title": str(entry.get("title") or "Untitled"),
                        "source_path": str(entry.get("source_path") or ""),
                    }
                    for score, entry in ranked
                ],
            }
        )
    return results


def compare_recall(
    source: Path, target: Path, questions_path: Path, top_k: int = 3
) -> dict[str, Any]:
    """Compare deterministic golden-question recall across two OKF bundles."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    questions = _load_questions(questions_path)
    source_entries = load_okf_bundle(source)["memories"]
    target_entries = load_okf_bundle(target)["memories"]
    source_results = _evaluate(source_entries, questions, top_k)
    target_results = _evaluate(target_entries, questions, top_k)
    source_hits = sum(result["hit"] for result in source_results)
    target_hits = sum(result["hit"] for result in target_results)
    regressions = [
        source_result["id"]
        for source_result, target_result in zip(
            source_results, target_results, strict=True
        )
        if source_result["hit"] and not target_result["hit"]
    ]
    total = len(questions)
    return {
        "questions": total,
        "top_k": top_k,
        "source_hits": source_hits,
        "target_hits": target_hits,
        "source_recall": source_hits / total,
        "target_recall": target_hits / total,
        "regressions": regressions,
        "is_recall_preserved": (
            source_hits == total and target_hits == total and not regressions
        ),
        "source_results": source_results,
        "target_results": target_results,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the golden-question parity command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original OKF bundle")
    parser.add_argument("target", type=Path, help="Round-tripped OKF bundle")
    parser.add_argument("questions", type=Path, help="Golden questions JSON")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 1 unless every golden answer is recalled before and after",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the parity check and return its CI-friendly process status."""
    args = _build_parser().parse_args(argv)
    if args.output:
        validate_report_output(args.source, args.target, args.output)
    report = compare_recall(args.source, args.target, args.questions, args.top_k)
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        write_report(args.output, output)
    else:
        print(output, end="")
    return 1 if args.fail_on_regression and not report["is_recall_preserved"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic source-checkpoint vs exported-OKF recall-parity validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from langgraph_checkpoint_to_okf import load_latest_checkpoints

GOLDEN_QUESTIONS = [
    {
        "question": "Which flight seat does Mira currently prefer?",
        "thread": "mira-travel",
        "channel": "preferences",
        "key": "flight_seat",
        "expected": "window",
    },
    {
        "question": "Where does Mira live?",
        "thread": "mira-travel",
        "channel": "profile",
        "key": "home_city",
        "expected": "Shanghai",
    },
    {
        "question": "Which database version does Atlas use?",
        "thread": "mira-work",
        "channel": "facts",
        "contains": "PostgreSQL 16",
        "expected": "PostgreSQL 16",
    },
    {
        "question": "Who owns launch-week on-call coverage?",
        "thread": "mira-work",
        "channel": "facts",
        "contains": "Priya",
        "expected": "Priya",
    },
    {
        "question": "How long is each focused study session?",
        "thread": "mira-learning",
        "channel": "preferences",
        "key": "study_session",
        "expected": "25 minutes",
    },
]


def _source_answer(source: dict[str, Any], question: dict[str, str]) -> str | None:
    value = source[question["thread"]][question["channel"]]
    if "key" in question:
        return str(value.get(question["key"]))
    needle = question["contains"]
    return next((str(item) for item in value if needle in str(item)), None)


def _okf_answer(bundle: Path, question: dict[str, str]) -> str | None:
    expected = question["expected"].lower()
    candidates = [
        path.read_text(encoding="utf-8")
        for path in sorted((bundle / "memories").glob("*.md"))
        if f"thread:{question['thread']}" in path.read_text(encoding="utf-8")
        and f"channel:{question['channel']}" in path.read_text(encoding="utf-8")
    ]
    return next(
        (question["expected"] for text in candidates if expected in text.lower()),
        None,
    )


def validate(database: Path, bundle: Path) -> dict[str, Any]:
    checkpoints = load_latest_checkpoints(database)
    source = {
        checkpoint.thread_id: dict(checkpoint.channel_values)
        for checkpoint in checkpoints
    }
    results: list[dict[str, Any]] = []
    for question in GOLDEN_QUESTIONS:
        source_answer = _source_answer(source, question)
        okf_answer = _okf_answer(bundle, question)
        passed = (
            source_answer is not None
            and question["expected"].lower() in source_answer.lower()
            and okf_answer == question["expected"]
        )
        results.append(
            {
                "question": question["question"],
                "expected": question["expected"],
                "source_answer": source_answer,
                "okf_answer": okf_answer,
                "passed": passed,
            }
        )
    passed_count = sum(result["passed"] for result in results)
    return {
        "source": str(database),
        "bundle": str(bundle),
        "passed": passed_count,
        "total": len(results),
        "recall_parity": passed_count / len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = validate(args.database, args.bundle)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

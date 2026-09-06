#!/usr/bin/env python3
"""Score the committed golden questions against live Memanto recall."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from memanto.app.config import settings
from memanto.cli.client.direct_client import DirectClient


def score_question(corpus: str, groups: list[list[str]]) -> tuple[bool, list[str]]:
    """Require one accepted term from every semantic term group."""
    lowered = corpus.casefold()
    missing = [
        " | ".join(group)
        for group in groups
        if not any(term.casefold() in lowered for term in group)
    ]
    return not missing, missing


def parse_args() -> argparse.Namespace:
    """Parse live-validator arguments."""
    parser = argparse.ArgumentParser(
        description="Score golden questions against live Memanto recall."
    )
    parser.add_argument("--agent", required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def recall_corpus(client: DirectClient, agent: str, question: str, limit: int) -> str:
    """Return a stable text corpus from one live semantic-recall response."""
    response = client.recall(
        agent_id=agent,
        query=question,
        limit=limit,
        min_similarity=0.0,
    )
    return json.dumps(
        response.get("memories") or [], ensure_ascii=False, sort_keys=True
    )


def main() -> int:
    """Query live Memanto and write an auditable recall report."""
    args = parse_args()
    api_key = (
        os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY or ""
    ).strip()
    if not api_key or api_key == "test-api-key":
        raise RuntimeError(
            "A real MOORCHEH_API_KEY is required for live recall validation."
        )

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise TypeError("Golden questions must be a JSON list.")

    client = DirectClient(api_key=api_key)
    client.activate_agent(args.agent)
    results: list[dict[str, Any]] = []
    for item in questions:
        corpus = recall_corpus(client, args.agent, item["question"], args.limit)
        passed, missing = score_question(corpus, item["required_terms"])
        results.append(
            {
                "question": item["question"],
                "expected_answer": item["answer"],
                "passed": passed,
                "missing_term_groups": missing,
            }
        )

    passed_count = sum(1 for result in results if result["passed"])
    report = {
        "agent": args.agent,
        "method": (
            "Live Memanto semantic recall. Each question passes when returned "
            "memories contain at least one accepted term from every semantic group."
        ),
        "passed": passed_count,
        "total": len(results),
        "recall_percent": round(100 * passed_count / max(len(results), 1), 1),
        "questions": results,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Ask Memanto the golden questions and save the unmodified RAG answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from memanto.cli.commands._shared import get_client


def query_memanto(agent: str, golden_file: Path, limit: int = 5) -> dict[str, Any]:
    client = get_client()
    cases = json.loads(golden_file.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in cases:
        response = client.answer(agent, case["question"], limit)
        answer = str(response.get("answer", ""))
        expected = [str(term) for term in case["expected_terms"]]
        passed = all(term.casefold() in answer.casefold() for term in expected)
        context = response.get("context_memories") or []
        results.append(
            {
                "question": case["question"],
                "answer": answer,
                "expected_terms": expected,
                "passed": passed,
                "context": [
                    {
                        "title": item.get("title"),
                        "score": item.get("score"),
                    }
                    for item in context
                    if isinstance(item, dict)
                ],
            }
        )
    passed = sum(result["passed"] for result in results)
    return {
        "system": "Memanto RAG",
        "agent": agent,
        "questions": len(results),
        "passed": passed,
        "score": passed / len(results) if results else 1.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--golden", type=Path, default=Path("golden_qa.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    report = query_memanto(args.agent, args.golden, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["score"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

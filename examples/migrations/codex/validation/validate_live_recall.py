#!/usr/bin/env python3
"""Query a live Memanto agent and score the Codex migration golden questions."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_recall import load_golden

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalized(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _memory_text(memory: dict[str, Any]) -> str:
    return "\n".join(
        (
            str(memory.get("title") or ""),
            str(memory.get("content") or ""),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score golden questions with live Memanto semantic recall."
    )
    parser.add_argument("--agent", required=True)
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).with_name("golden_qa.json"),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from memanto.cli.commands._shared import config_manager, get_client
    except ImportError as exc:
        raise SystemExit(
            "memanto must be installed to run live recall validation"
        ) from exc

    active_agent, _ = config_manager.get_active_session()
    if active_agent != args.agent:
        raise SystemExit(
            f"activate {args.agent!r} before validation: "
            f"memanto agent activate {args.agent}"
        )

    client = get_client()
    golden = load_golden(args.golden)
    results = []
    for item in golden:
        response = client.recall(
            agent_id=args.agent,
            query=str(item["question"]),
            limit=args.limit,
            min_similarity=0.0,
        )
        memories = response.get("memories") or []
        recalled = "\n".join(
            _memory_text(memory) for memory in memories if isinstance(memory, dict)
        )
        normalized = _normalized(recalled)
        expected = [str(term) for term in item["expected_all"]]
        missing = [term for term in expected if _normalized(term) not in normalized]
        results.append(
            {
                "question_id": str(item["id"]),
                "question": str(item["question"]),
                "passed": not missing,
                "expected_all": expected,
                "missing": missing,
                "returned_memories": len(memories),
            }
        )

    passed = sum(result["passed"] for result in results)
    score = round(100 * passed / len(results), 1) if results else 0.0
    report = {
        "schema": "codex-memanto-live-recall/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": args.agent,
        "score": score,
        "questions": len(results),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Live Memanto recall: {score:.1f}% ({passed}/{len(results)})")
    print(f"Report: {args.report}")
    return 0 if score == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

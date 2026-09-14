#!/usr/bin/env python3
"""
Round-trip recall validation: golden Q&A against a migrated Memanto agent.

After importing the OKF bundle for real::

    memanto migrate okf ./sample_output/okf-bundle --agent <agent-id>

run this script to prove zero amnesia — every question a well-used ChatGPT
account could answer from its memory should now be answerable by Memanto::

    python3 validate_recall.py [--agent <agent-id>] [--qa golden_qa.json]

Requires a configured Memanto CLI (``MOORCHEH_API_KEY``) and an active or
``--agent``-specified agent. Grading is deliberately dumb-simple keyword
matching so results are reproducible without an LLM judge: an answer passes
when every keyword *group* matches (groups are AND-ed, alternatives within
a group are OR-ed, case-insensitive).

For the "before" half of the comparison, ask the same questions in the
source ChatGPT account and grade the answers with the same keyword rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def grade(answer: str, expected_keywords: list[list[str]]) -> bool:
    lowered = answer.lower()
    return all(
        any(alternative.lower() in lowered for alternative in group)
        for group in expected_keywords
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent", default=None, help="Memanto agent id (defaults to active agent)"
    )
    parser.add_argument(
        "--qa",
        type=Path,
        default=Path(__file__).parent / "golden_qa.json",
        help="Golden Q&A file",
    )
    args = parser.parse_args()

    from memanto.cli.commands._shared import config_manager, get_client

    agent_id = args.agent
    if not agent_id:
        agent_id, _ = config_manager.get_active_session()
    if not agent_id:
        print(
            "No agent: pass --agent <id> or run 'memanto agent activate <id>' first.",
            file=sys.stderr,
        )
        return 2

    qa_set = json.loads(args.qa.read_text(encoding="utf-8"))
    questions = qa_set["questions"]
    client = get_client()

    passed = 0
    print(
        f"Round-trip recall validation — agent '{agent_id}', "
        f"{len(questions)} questions\n"
    )
    for item in questions:
        try:
            result = client.answer(agent_id, item["question"])
            answer = (result or {}).get("answer", "") or ""
        except Exception as exc:  # noqa: BLE001 — report and keep scoring
            answer = f"<error: {exc}>"

        is_ok = grade(answer, item["expected_keywords"])
        passed += int(is_ok)
        status = "PASS" if is_ok else "FAIL"
        print(f"[{status}] {item['id']}: {item['question']}")
        print(f"       -> {' '.join(answer.split())[:160]}\n")

    total = len(questions)
    print(f"Recall parity: {passed}/{total} ({100 * passed // max(total, 1)}%)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

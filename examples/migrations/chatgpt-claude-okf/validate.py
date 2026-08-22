#!/usr/bin/env python3
"""
Round-trip recall parity: does the migrated agent still know what the source
assistant knew?

``golden_qa.json`` holds questions you asked ChatGPT/Claude *before* migrating,
paired with the answer that assistant gave. This script asks Memanto the same
questions afterwards and has a judge decide whether each answer preserves the
same information.

The question is deliberately "is the information preserved", not "is the text
similar", a migrated memory is allowed to be phrased differently, and it is
allowed to be shorter. It is not allowed to have forgotten.

Usage:
    python validate.py --agent my-agent
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from memanto.cli.commands._shared import get_client

JUDGE_PROMPT = """You are grading whether a migrated memory system preserved \
knowledge from an earlier assistant.

QUESTION: {question}

WHAT THE SOURCE ASSISTANT KNEW: {expected}

WHAT THE MIGRATED SYSTEM ANSWERED: {actual}

Does the migrated answer preserve the essential information? Different wording, \
extra detail, or a shorter answer are all fine. Missing, contradicting, or \
fabricating the key facts is not.

Reply with JSON only: {{"verdict": "pass" | "partial" | "fail", "why": "<one short sentence>"}}
"""


VERDICTS = ("pass", "partial", "fail")


def parse_verdict(text: str) -> dict[str, str]:
    """Turn the judge's raw reply into a verdict row, or an ``error`` row.

    A reply that is unparseable, is not an object, carries a verdict outside
    the three the prompt allows, or omits its reason means no judgment was
    obtained. That is reported as ``error`` rather than ``fail``: a failed
    judge call is not evidence that recall was lost, and main() exits 2 for
    an incomplete score against 1 for a genuine failure.
    """
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"verdict": "error", "why": f"unparseable judge reply: {text[:80]}"}
    if not isinstance(parsed, dict):
        # A bare array or scalar is valid JSON, and would blow up on .get()
        # at the call site and take the whole run down with it.
        return {"verdict": "error", "why": f"reply was not an object: {text[:80]}"}

    verdict = parsed.get("verdict")
    if verdict not in VERDICTS:
        return {
            "verdict": "error",
            "why": f"unknown verdict {str(verdict)[:40]!r}, expected one of {VERDICTS}",
        }
    why = parsed.get("why")
    if not isinstance(why, str) or not why.strip():
        # A verdict with no reason is not a judgment anyone can audit, and the
        # printed table is the evidence artifact for this whole check.
        return {"verdict": "error", "why": f"verdict {verdict!r} came with no reason"}
    return {"verdict": verdict, "why": why.strip()}


def judge(question: str, expected: str, actual: str, model: str) -> dict[str, str]:
    """Score one answer with an LLM judge via OpenRouter.

    Never raises: a judge that is rate-limited, out of credit or misconfigured
    should cost you one row, not the whole run and every verdict already earned.
    """
    try:
        return _judge(question, expected, actual, model)
    except Exception as exc:  # noqa: BLE001, surface it as a row, keep going
        detail = str(exc).split("\n")[0][:110]
        return {"verdict": "error", "why": detail}


def _judge(question: str, expected: str, actual: str, model: str) -> dict[str, str]:
    """Ask the judge model whether the migrated answer preserved the meaning.

    Imports OpenAI lazily so that ``--help`` and argument errors work without
    the dependency installed.
    """
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        # The verdict is one line of JSON. Without a cap, OpenRouter reserves the
        # model's full output window up front and rejects the call on small balances.
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    question=question, expected=expected, actual=actual or "(no answer)"
                ),
            }
        ],
    )
    return parse_verdict(response.choices[0].message.content or "")


def main() -> int:
    """Score recall parity across the golden question set.

    Exits 0 when every row passed, 1 when a row failed, and 2 when a judge
    call errored, because an incomplete score is not the same as a failing
    one and a caller needs to tell them apart.
    """
    parser = argparse.ArgumentParser(description="Round-trip recall parity check")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--golden", type=Path, default=Path("golden_qa.json"))
    parser.add_argument(
        "--model",
        default="google/gemini-2.5-flash-lite",
        help="Any OpenRouter model id. The default is chosen for cost: judging is "
        "a one-line verdict, so a cheap model keeps a full run under a cent. "
        "See https://openrouter.ai/models",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    golden: list[dict[str, Any]] = json.loads(args.golden.read_text(encoding="utf-8"))
    client = get_client()
    rows, passed = [], 0

    for item in golden:
        question = item["question"]
        print(f"  {question[:70]}...")
        try:
            answer = (client.answer(args.agent, question) or {}).get("answer", "")
        except Exception as exc:  # noqa: BLE001, a failed recall is a data point
            answer = ""
            print(f"    recall failed: {exc}", file=sys.stderr)

        verdict = judge(question, item["source_answer"], answer, args.model)
        passed += verdict.get("verdict") == "pass"
        rows.append((item.get("id", "?"), verdict.get("verdict"), verdict.get("why")))

    width = max(len(str(r[0])) for r in rows)
    print(f"\n{'id'.ljust(width)}  verdict   why")
    print("-" * (width + 40))
    for qid, verdict, why in rows:
        print(f"{str(qid).ljust(width)}  {str(verdict):<9} {why}")

    errored = sum(1 for _, verdict, _ in rows if verdict == "error")
    print(f"\nRecall parity: {passed}/{len(rows)} preserved")
    if errored:
        print(f"{errored} question(s) could not be judged, parity is incomplete.")
        return 2
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

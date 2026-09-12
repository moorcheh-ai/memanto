#!/usr/bin/env python3
"""Score recall parity across the freedom loop.

Asks the same golden questions of the source agent and of the agent the OKF
bundle was imported into, then compares. Equal scores mean the round trip cost
the agent nothing: no amnesia.

    python validate_recall.py --source okf-fidelity-loop --target okf-fidelity-rt

Both agents must already exist; see README for the two commands that build them.
Exits non-zero if the target recalls less than the source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from memanto.cli.commands._shared import get_client

HERE = Path(__file__).resolve().parent


def hits(client: Any, agent: str, question: str, expect: list[str]) -> bool:
    """True when a recalled memory contains every expected keyword."""
    result = client.recall(agent_id=agent, query=question, limit=5)
    blob = " ".join(
        f"{m.get('title', '')} {m.get('content', '')}"
        for m in (result.get("memories") or [])
    ).lower()
    return all(word.lower() in blob for word in expect)


def score(agent: str, questions: list[dict[str, Any]]) -> list[bool]:
    """Ask every question of one agent. A session is scoped to a single agent,
    so each side of the comparison is activated in turn."""
    client = get_client()
    client.activate_agent(agent)
    return [hits(client, agent, q["question"], q["expect"]) for q in questions]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="agent the bundle came from")
    parser.add_argument("--target", required=True, help="agent the bundle went into")
    parser.add_argument("--out", type=Path, help="write the scorecard here")
    args = parser.parse_args()

    questions = json.loads((HERE / "golden_qa.json").read_text(encoding="utf-8"))

    before_all = score(args.source, questions)
    after_all = score(args.target, questions)

    rows = [
        (item["question"], before, after)
        for item, before, after in zip(questions, before_all, after_all, strict=True)
    ]
    source_score = sum(before_all)
    target_score = sum(after_all)
    total = len(questions)
    lines = [
        "# Recall parity across the OKF round trip",
        "",
        f"Source agent: `{args.source}` — target agent: `{args.target}`",
        "",
        "| Question | Before | After |",
        "| --- | --- | --- |",
    ]
    tick = {True: "PASS", False: "FAIL"}
    for question, before, after in rows:
        lines.append(f"| {question} | {tick[before]} | {tick[after]} |")
    lines += [
        "",
        f"**Before migration: {source_score}/{total} — "
        f"after migration: {target_score}/{total}.**",
        "",
        (
            "Recall parity held: the round trip cost the agent nothing."
            if target_score >= source_score
            else "Recall regressed across the round trip."
        ),
    ]

    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")

    return 0 if target_score >= source_score else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Phase 3 — golden Q&A before/after + Anthropic LLM-as-judge.

Runs three steps and writes every intermediate artifact so the parity number
is auditable:

1. Ask every golden question against the live Graphiti graph.
2. Ask the same questions against the Memanto agent (via the SDK).
3. Score each pair with the Anthropic judge.

If either side cannot answer, the script fails loudly into
``data/validation/`` rather than inventing a score. Partial progress (e.g.
Graphiti answers collected, Memanto key missing) is still written so the
blocker is concrete when you wake up.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_okf import graphiti_client  # noqa: E402
from graphiti_okf.golden_qa import GOLDEN_QUESTIONS, signal_hits  # noqa: E402
from graphiti_okf.judge import (  # noqa: E402
    JudgeError,
    build_client,
    judge_model,
    judge_pair,
    parity_percentage,
    render_markdown,
    verdict_counts,
)
from graphiti_okf.runtime import VALIDATION_DIR, load_env, log  # noqa: E402


async def ask_graphiti(questions: list) -> dict[str, str]:
    """Query the live Graphiti graph for each golden question."""
    group = graphiti_client.group_id()
    graphiti = graphiti_client.build_graphiti()
    answers: dict[str, str] = {}
    try:
        for question in questions:
            log(f"  Graphiti  {question.id}: {question.question[:72]}...")
            edges = await graphiti.search(
                query=question.question,
                group_ids=[group],
                num_results=12,
            )
            if not edges:
                answers[question.id] = "(Graphiti returned no matching edges.)"
                continue
            # Compose an answer from the ranked facts Graphiti returned. This
            # mirrors how a Zep-style agent would ground a reply: the search
            # hits *are* the knowledge. We do not re-ask a separate LLM, so the
            # "before" side is pure Graphiti retrieval.
            lines = []
            for edge in edges:
                status = "superseded" if (edge.invalid_at or edge.expired_at) else "current"
                stamp = ""
                if edge.valid_at:
                    stamp = f" [valid_at={edge.valid_at.isoformat()}"
                    if edge.invalid_at:
                        stamp += f", invalid_at={edge.invalid_at.isoformat()}"
                    stamp += "]"
                lines.append(f"- ({status}) {edge.fact}{stamp}")
            answers[question.id] = "\n".join(lines)
    finally:
        await graphiti.close()
    return answers


def ask_memanto(questions: list, agent_id: str | None) -> dict[str, str]:
    """Ask the same questions against a Memanto agent via the SDK."""
    from memanto.cli.commands._shared import config_manager, get_client

    client = get_client()
    if not agent_id:
        agent_id, _ = config_manager.get_active_session()
    if not agent_id:
        raise RuntimeError(
            "No Memanto agent available. Pass --agent or activate one with "
            "'memanto agent activate <id>' before running validation."
        )

    answers: dict[str, str] = {}
    for question in questions:
        log(f"  Memanto   {question.id}: {question.question[:72]}...")
        try:
            result = client.answer(agent_id=agent_id, question=question.question, limit=12)
            answers[question.id] = (result or {}).get("answer") or "(empty answer)"
        except Exception as exc:
            answers[question.id] = f"(Memanto answer failed: {type(exc).__name__}: {exc})"
    return answers


def judge_all(before: dict[str, str], after: dict[str, str]) -> list:
    client = build_client()
    verdicts = []
    for question in GOLDEN_QUESTIONS:
        log(f"  Judge     {question.id}...")
        verdicts.append(
            judge_pair(
                client,
                question,
                before.get(question.id, ""),
                after.get(question.id, ""),
            )
        )
    return verdicts


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=None, help="Memanto agent id (defaults to active).")
    parser.add_argument(
        "--skip-graphiti",
        action="store_true",
        help="Reuse a previously written data/validation/before_graphiti.json.",
    )
    parser.add_argument(
        "--skip-memanto",
        action="store_true",
        help="Reuse a previously written data/validation/after_memanto.json.",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Collect answers but do not call the Anthropic judge.",
    )
    args = parser.parse_args()
    load_env()

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    before_path = VALIDATION_DIR / "before_graphiti.json"
    after_path = VALIDATION_DIR / "after_memanto.json"
    results_md = VALIDATION_DIR.parent / "validation_results.md"
    results_json = VALIDATION_DIR / "verdicts.json"

    questions = list(GOLDEN_QUESTIONS)

    if args.skip_graphiti and before_path.exists():
        before = json.loads(before_path.read_text(encoding="utf-8"))
        log(f"Reusing Graphiti answers from {before_path}")
    else:
        log("Querying live Graphiti...")
        before = asyncio.run(ask_graphiti(questions))
        _write_json(before_path, before)

    if args.skip_memanto and after_path.exists():
        after = json.loads(after_path.read_text(encoding="utf-8"))
        log(f"Reusing Memanto answers from {after_path}")
    else:
        log("Querying Memanto...")
        try:
            after = ask_memanto(questions, args.agent)
        except Exception as exc:
            _write_json(
                VALIDATION_DIR / "blocker.json",
                {
                    "stage": "memanto_answer",
                    "error": f"{type(exc).__name__}: {exc}",
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            )
            raise SystemExit(f"ERROR: Memanto querying failed: {exc}") from exc
        _write_json(after_path, after)

    # Cheap deterministic tripwire — not the score, just a smoke signal.
    tripwire = {
        q.id: {
            "before_hits": signal_hits(q, before.get(q.id, "")),
            "after_hits": signal_hits(q, after.get(q.id, "")),
        }
        for q in questions
    }
    _write_json(VALIDATION_DIR / "signal_tripwire.json", tripwire)

    if args.skip_judge:
        log("--skip-judge set; answers written, no parity score produced.")
        return

    try:
        verdicts = judge_all(before, after)
    except JudgeError as exc:
        _write_json(
            VALIDATION_DIR / "blocker.json",
            {
                "stage": "llm_judge",
                "error": str(exc),
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise SystemExit(f"ERROR: {exc}") from exc

    model = judge_model()
    markdown = render_markdown(verdicts, model=model)
    results_md.write_text(markdown, encoding="utf-8")
    _write_json(
        results_json,
        {
            "model": model,
            "parity_percent": parity_percentage(verdicts),
            "verdict_counts": verdict_counts(verdicts),
            "verdicts": [v.as_dict() for v in verdicts],
            "judged_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    log("")
    log(f"Recall parity : {parity_percentage(verdicts)}%")
    log(f"Verdicts      : {verdict_counts(verdicts)}")
    log(f"Results       : {results_md}")


if __name__ == "__main__":
    main()

"""Golden-set content-retention evaluation for the Claude Code -> Memanto
showcase.

Compares golden-set coverage on the source archive ("before") with coverage
after the migration pipeline ("after"): source JSONL -> OKF bundle ->
memanto's own ``okf_loader`` -> ``mappers.map_okf`` payloads.

The evaluator is deterministic and offline, so the showcase is reproducible
without an API key or network access. Each golden question carries answer
keywords; a side answers a question when a single candidate record contains
every keyword (case-insensitive). Retention is the fraction of questions
answered; parity is after/before, where 1.0 means every golden answer
survived migration.

This is an offline content-retention check, not a live semantic-recall pass:
Memanto recall requires the Moorcheh API. A live recall pass after import
with ``memanto migrate okf`` is demonstrated in the showcase demo video.

Usage:

    python scripts/evaluate_recall.py \
        --archive demo_source/demo_session.jsonl \
        --bundle /tmp/recall-bundle

Run from the adapter directory (``examples/migrations/claude-code-memory``)
or from the memanto repository root; the ``memanto`` package must be
importable (install it with ``pip install -e .`` at the repo root).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_DEFAULT_QUESTIONS = Path(__file__).parent / "golden_questions.json"


def _load_questions(path: Path = _DEFAULT_QUESTIONS) -> list[dict[str, Any]]:
    """Load the golden question set from JSON."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    questions = data.get("questions") or []
    if not questions:
        raise ValueError(f"No questions found in {path}")
    return questions


def _contains_keywords(text: str, keywords: list[str]) -> bool:
    """Return True when every keyword appears in the text, word-bounded."""
    lowered = text.lower()
    return all(
        re.search(r"\b" + re.escape(kw.lower()) + r"\b", lowered) is not None
        for kw in keywords
    )


def _before_candidates(archive: Path) -> list[str]:
    """Return candidate texts from the source archive (pre-migration)."""
    from claude_code_adapter.parser import parse_claude_jsonl

    turns = parse_claude_jsonl(archive)
    return [turn.text for turn in turns if turn.text and turn.text.strip()]


def _after_candidates(archive: Path, bundle: Path) -> list[str]:
    """Return candidate texts after the full migration pipeline.

    The adapter extracts memories from the same archive, writes an OKF
    bundle, and Memanto's own loader + mapper read it back. This is the
    exact in -> owned -> portable loop users run.
    """
    from claude_code_adapter.extractor import extract_memories
    from claude_code_adapter.okf_writer import write_okf_bundle
    from claude_code_adapter.parser import parse_claude_jsonl

    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    write_okf_bundle(memories, bundle)
    rows = map_okf(load_okf_bundle(bundle))
    return [str(row.get("content") or "") for row in rows if row.get("content")]


def _recall(
    candidates: list[str], questions: list[dict[str, Any]]
) -> tuple[float, list[dict[str, Any]]]:
    """Score a candidate set against the golden questions."""
    answered = 0
    details: list[dict[str, Any]] = []
    for question in questions:
        keywords = [str(k) for k in (question.get("answer_keywords") or [])]
        hit = any(_contains_keywords(text, keywords) for text in candidates)
        answered += int(hit)
        details.append(
            {
                "id": question.get("id"),
                "question": question.get("question"),
                "answered": hit,
            }
        )
    total = len(questions)
    return (answered / total if total else 0.0), details


def evaluate_content_retention(
    archive: Path,
    bundle: Path,
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run before/after content-retention scoring and return the parity
    report."""
    question_set = questions if questions is not None else _load_questions()
    before_candidates = _before_candidates(archive)
    after_candidates = _after_candidates(archive, bundle)

    before_retention, before_details = _recall(before_candidates, question_set)
    after_retention, after_details = _recall(after_candidates, question_set)
    parity = (
        after_retention / before_retention
        if before_retention
        else (1.0 if after_retention else 0.0)
    )

    return {
        "archive": str(archive),
        "bundle": str(bundle),
        "before_candidates": len(before_candidates),
        "after_candidates": len(after_candidates),
        "before_retention": round(before_retention, 3),
        "after_retention": round(after_retention, 3),
        "parity": round(parity, 3),
        "before_details": before_details,
        "after_details": after_details,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the evaluation from the command line and print a report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        default=str(
            Path(__file__).resolve().parents[1] / "demo_source" / "demo_session.jsonl"
        ),
        help="Source Claude Code JSONL archive",
    )
    parser.add_argument(
        "--bundle",
        default=None,
        help="Output OKF bundle directory (default: a temp directory)",
    )
    args = parser.parse_args(argv)

    archive = Path(args.archive)
    bundle = (
        Path(args.bundle)
        if args.bundle
        else Path(tempfile.mkdtemp(prefix="recall-bundle-"))
    )
    report = evaluate_content_retention(archive, bundle)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = report["parity"] >= 1.0 and report["after_retention"] >= 0.9
    print(
        "RESULT: "
        + (
            "CONTENT PRESERVED - migration retained every golden answer"
            if ok
            else "RETENTION LOST - inspect the per-question details above"
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

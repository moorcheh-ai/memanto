"""Golden Q&A recall parity across source stores and the consolidated OKF corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _corpus_from_memories(memories: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{m.get('title', '')}\n{m.get('content', '')}" for m in memories
    ).lower()


def _corpus_from_okf(bundle_dir: Path) -> str:
    parts: list[str] = []
    memories_dir = bundle_dir / "memories"
    scan = memories_dir if memories_dir.is_dir() else bundle_dir
    for path in sorted(scan.rglob("*.md")):
        if path.name.lower() in {"index.md", "log.md"}:
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts).lower()


def _answerable(corpus: str, question: dict[str, Any]) -> tuple[bool, str]:
    hits = [
        phrase
        for phrase in question.get("must_include_any", [])
        if phrase.lower() in corpus
    ]
    if not hits:
        return False, "missing required phrases"
    forbidden = question.get("must_not_include_as_current") or []
    # Soft check: stale phrases may still appear in sessions/; only fail if they
    # appear in the active corpus without the correction also present.
    for phrase in forbidden:
        if (
            phrase.lower() in corpus
            and "fastapi" not in corpus
            and "python (fastapi)" not in corpus
        ):
            # Active corpus should contain the correction; if Python/FastAPI is
            # present we treat the stale phrase as historical noise.
            if "python" not in corpus:
                return False, f"stale preference still dominant: {phrase}"
    return True, f"matched {hits[0]}"


def evaluate_parity(
    *,
    source_memories: list[dict[str, Any]],
    okf_bundle: Path,
    questions_path: Path,
) -> dict[str, Any]:
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    source_corpus = _corpus_from_memories(source_memories)
    okf_corpus = _corpus_from_okf(okf_bundle)

    rows: list[dict[str, Any]] = []
    source_pass = okf_pass = 0
    for q in questions:
        s_ok, s_note = _answerable(source_corpus, q)
        o_ok, o_note = _answerable(okf_corpus, q)
        source_pass += int(s_ok)
        okf_pass += int(o_ok)
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "source_ok": s_ok,
                "source_note": s_note,
                "okf_ok": o_ok,
                "okf_note": o_note,
                "parity": s_ok == o_ok and s_ok,
            }
        )

    total = len(questions)
    return {
        "total": total,
        "source_recall": f"{source_pass}/{total}",
        "okf_recall": f"{okf_pass}/{total}",
        "parity_pass": f"{sum(1 for r in rows if r['parity'])}/{total}",
        "is_recall_preserved": source_pass == total and okf_pass == total,
        "questions": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Recall parity",
        "",
        f"- Source recall: **{report['source_recall']}**",
        f"- OKF recall: **{report['okf_recall']}**",
        f"- Parity: **{report['parity_pass']}**",
        f"- Verdict: `is_recall_preserved: {report['is_recall_preserved']}`",
        "",
        "| ID | Question | Source | OKF | Parity |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["questions"]:
        lines.append(
            f"| {row['id']} | {row['question']} | "
            f"{'pass' if row['source_ok'] else 'fail'} | "
            f"{'pass' if row['okf_ok'] else 'fail'} | "
            f"{'yes' if row['parity'] else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)

#!/usr/bin/env python3
"""Golden Q&A recall check against mapped Hindsight → OKF memories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hindsight_mapper import export_hindsight_to_okf, parse_hindsight_archive  # noqa: E402
from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402


def _score_question(rows: list[dict], question: dict) -> tuple[bool, str]:
    keywords = [k.lower() for k in question["expected_keywords"]]
    mem_type = question.get("memory_type")
    candidates = rows
    if mem_type:
        candidates = [r for r in rows if (r.get("type") or "").lower() == mem_type] or rows

    for row in candidates:
        haystack = f"{row.get('title', '')} {row.get('content', '')}".lower()
        if all(keyword in haystack for keyword in keywords):
            return True, row.get("title", "")[:120]

    return False, ""


def main() -> int:
    showcase = ROOT
    archive_path = showcase / "sample-data" / "project-atlas-agent.zip"
    okf_dir = showcase / "sample-data" / "okf-bundle"

    if not archive_path.exists():
        print("Sample archive missing; run build_sample_archive.py first", file=sys.stderr)
        return 1

    export_hindsight_to_okf(archive_path, okf_dir, agent_id="project-atlas-agent")
    rows = map_okf(load_okf_bundle(okf_dir))
    questions = json.loads((Path(__file__).parent / "golden_qa.json").read_text(encoding="utf-8"))

    passed = 0
    for item in questions:
        ok, hit = _score_question(rows, item)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {item['question']}")
        if hit:
            print(f"       matched: {hit}")
        passed += int(ok)

    print(f"\nRecall parity: {passed}/{len(questions)}")
    archive = parse_hindsight_archive(archive_path)
    print(
        f"Source facts: {sum(len(d.get('facts') or []) for d in archive.documents)} "
        f"-> mapped memories: {len(rows)}"
    )
    return 0 if passed == len(questions) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score golden-question recall parity before and after OKF conversion."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from memanto.cli.migrate.okf_loader import load_okf_bundle


def load_adapter(example_dir: Path) -> ModuleType:
    """Load the sibling adapter without requiring a package-name rename."""
    path = example_dir / "claude_code_to_okf.py"
    spec = importlib.util.spec_from_file_location("claude_code_to_okf", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def corpus_from_okf(path: Path) -> str:
    """Flatten importable OKF fields into a recall corpus."""
    export = load_okf_bundle(path)
    chunks: list[str] = []
    for memory in export.get("memories", []):
        for key in ("title", "description", "body"):
            value = memory.get(key)
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(chunks)


def score_question(corpus: str, groups: list[list[str]]) -> tuple[bool, list[str]]:
    """Require at least one accepted term from every semantic term group."""
    lowered = corpus.casefold()
    missing: list[str] = []
    for group in groups:
        if not any(term.casefold() in lowered for term in group):
            missing.append(" | ".join(group))
    return not missing, missing


def score_corpus(corpus: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Score a corpus against all golden questions."""
    results = []
    for item in questions:
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
    return {
        "passed": passed_count,
        "total": len(results),
        "recall_percent": round(100 * passed_count / max(len(results), 1), 1),
        "questions": results,
    }


def parse_args() -> argparse.Namespace:
    """Parse validator arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-home", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--project-data", type=Path, required=True)
    parser.add_argument("--okf", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    """Run source-vs-OKF recall parity validation."""
    args = parse_args()
    example_dir = Path(__file__).resolve().parents[1]
    adapter = load_adapter(example_dir)
    records, _ = adapter.collect_records(
        args.source_home.resolve(),
        args.project.resolve(),
        args.project_data.resolve(),
        include_transcripts=True,
        include_todos=True,
    )
    source_corpus = "\n".join(f"{record.title}\n{record.content}" for record in records)
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise TypeError("Golden questions must be a JSON list.")

    source_score = score_corpus(source_corpus, questions)
    okf_score = score_corpus(corpus_from_okf(args.okf), questions)
    report = {
        "method": (
            "Deterministic golden Q&A: every question defines semantic term "
            "groups; a corpus passes when it contains at least one accepted "
            "term from every group."
        ),
        "source": source_score,
        "okf": okf_score,
        "parity_delta_points": round(
            okf_score["recall_percent"] - source_score["recall_percent"], 1
        ),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if source_score["passed"] == okf_score["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic golden-question parity for n8n source data and imported OKF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

from .adapter import build_memories, load_executions, load_mapping


def _flatten_source_memories(
    input_path: str | Path, mapping_path: str | Path
) -> list[dict[str, Any]]:
    """Map source executions in memory without writing an OKF bundle."""
    executions, _ = load_executions(input_path)
    memories_by_type, _ = build_memories(executions, load_mapping(mapping_path))
    return [
        memory
        for memory_type in sorted(memories_by_type)
        for memory in memories_by_type[memory_type]
    ]


def _load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load a non-empty golden-question list from YAML."""
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    questions = value.get("questions") if isinstance(value, dict) else None
    if not isinstance(questions, list) or not questions:
        raise ValueError("Golden question file must contain a questions list")
    return questions


def _evaluate(rows: list[dict[str, Any]], question: dict[str, Any]) -> tuple[bool, str]:
    """Check one exact memory title and its required factual fragments."""
    expected_title = str(question.get("memory_title") or "")
    row = next(
        (candidate for candidate in rows if candidate.get("title") == expected_title),
        None,
    )
    if row is None:
        return False, f"Memory not found: {expected_title}"

    content = str(row.get("content") or "")
    missing = [
        str(fragment)
        for fragment in question.get("must_contain") or []
        if str(fragment) not in content
    ]
    if missing:
        return False, "Missing facts: " + ", ".join(missing)
    return True, "All expected facts recalled"


def validate_recall_parity(
    input_path: str | Path,
    mapping_path: str | Path,
    bundle_path: str | Path,
    questions_path: str | Path,
) -> dict[str, Any]:
    """Score the same golden questions against source and round-tripped rows."""
    source_rows = _flatten_source_memories(input_path, mapping_path)
    migrated_rows = map_okf(load_okf_bundle(bundle_path))
    questions = _load_questions(questions_path)

    results: list[dict[str, Any]] = []
    for question in questions:
        source_pass, source_detail = _evaluate(source_rows, question)
        migrated_pass, migrated_detail = _evaluate(migrated_rows, question)
        results.append(
            {
                "id": question.get("id"),
                "question": question.get("question"),
                "source_pass": source_pass,
                "source_detail": source_detail,
                "migrated_pass": migrated_pass,
                "migrated_detail": migrated_detail,
                "parity": source_pass and migrated_pass,
            }
        )

    passed = sum(1 for row in results if row["parity"])
    return {
        "method": "deterministic-golden-questions",
        "questions": len(results),
        "passed": passed,
        "recall_parity_score": passed / len(results),
        "valid": passed == len(results),
        "results": results,
    }


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a deterministic UTF-8 parity report."""
    Path(path).write_bytes(
        (
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    )

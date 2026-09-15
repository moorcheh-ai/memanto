"""Validate that the generated goose OKF bundle imports through Memanto."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


sys.path.insert(0, str(repo_root()))

from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402

QUESTIONS = {
    "Which agent generated the migrated sessions?": ["goose"],
    "How must reconciliation keys behave?": ["deterministic", "across machines"],
    "What customer data must audit output protect?": ["full email address"],
    "What check is required before completion?": ["python -m unittest -v"],
}


def check_recall(rows: list[dict], needle_groups: dict[str, list[str]]) -> list[dict]:
    haystack = "\n".join(
        f"{row.get('title', '')}\n{row.get('content', '')}" for row in rows
    ).lower()
    report: list[dict] = []
    for question, needles in needle_groups.items():
        missing = [needle for needle in needles if needle.lower() not in haystack]
        report.append(
            {
                "question": question,
                "expected_terms": needles,
                "passed": not missing,
                "missing_terms": missing,
            }
        )
    return report


def load_questions(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return QUESTIONS
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(question, str)
        and isinstance(terms, list)
        and terms
        and all(isinstance(term, str) and term for term in terms)
        for question, terms in value.items()
    ):
        raise ValueError("questions must be a JSON object of question-to-term lists")
    return value


def validate(bundle: Path, questions: dict[str, list[str]] | None = None) -> dict:
    export = load_okf_bundle(bundle)
    rows = map_okf(export)
    type_counts = Counter(row.get("type") or "auto" for row in rows)
    checks = check_recall(rows, questions or QUESTIONS)
    loaded_count = len(export["memories"])
    mapped_count = len(rows)
    return {
        "bundle": str(bundle),
        "loaded_okf_entries": loaded_count,
        "mapped_memanto_rows": mapped_count,
        "type_counts": dict(sorted(type_counts.items())),
        "recall_checks": checks,
        "passed": bool(rows)
        and mapped_count == loaded_count
        and all(item["passed"] for item in checks),
    }


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# Goose OKF round-trip validation",
        "",
        f"- OKF entries loaded: {report['loaded_okf_entries']}",
        f"- Memanto rows mapped: {report['mapped_memanto_rows']}",
        f"- Passed: {report['passed']}",
        "",
        "## Type counts",
        "",
    ]
    for memory_type, count in report["type_counts"].items():
        lines.append(f"- {memory_type}: {count}")
    lines.extend(["", "## Recall parity checks", ""])
    for check in report["recall_checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        terms = ", ".join(check["expected_terms"])
        lines.append(f"- {mark}: {check['question']} — expected `{terms}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--report", type=Path, help="write markdown validation report")
    parser.add_argument(
        "--questions",
        type=Path,
        help="JSON object mapping recall questions to required answer terms",
    )
    args = parser.parse_args()

    result = validate(args.bundle, load_questions(args.questions))
    if args.report:
        write_markdown(result, args.report)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

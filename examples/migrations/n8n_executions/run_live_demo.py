"""Guarded Memanto cloud import, recall, and OKF export demonstration.

The Moorcheh API key is read only from ``MOORCHEH_API_KEY`` in the process
environment. It is never accepted as a command-line option, printed, or written
to the validation report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.cli.migrate.okf_loader import load_okf_bundle

HERE = Path(__file__).resolve().parent
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def build_command_plan(
    agent_id: str,
    bundle: Path,
    export_path: Path,
    *,
    reuse_agent: bool,
    activation_hours: int,
) -> list[dict[str, Any]]:
    """Build a secret-free description of the exact shipped CLI commands."""
    base = [sys.executable, "-m", "memanto"]
    activation = (
        [*base, "agent", "activate", agent_id, "--hours", str(activation_hours)]
        if reuse_agent
        else [
            *base,
            "agent",
            "create",
            agent_id,
            "--pattern",
            "tool",
            "--description",
            "n8n execution history migration demo",
        ]
    )
    return [
        {"label": "activate-agent", "argv": activation},
        {
            "label": "import-okf",
            "argv": [
                *base,
                "migrate",
                "okf",
                str(bundle),
                "--agent",
                agent_id,
            ],
        },
        {
            "label": "export-okf",
            "argv": [
                *base,
                "memory",
                "export",
                "--agent",
                agent_id,
                "--okf",
                "--split",
                "type",
                "--output",
                str(export_path),
            ],
        },
    ]


def _clean_output(value: str, private_roots: list[Path]) -> str:
    """Strip terminal control codes and redact machine-specific absolute paths."""
    cleaned = _ANSI_RE.sub("", value).replace("\\", "/")
    for root in private_roots:
        rendered = str(root.resolve()).replace("\\", "/")
        cleaned = cleaned.replace(rendered, "<private-path>")
    return cleaned.strip()


def _run(
    argv: list[str],
    *,
    env: dict[str, str],
    private_roots: list[Path],
) -> str:
    """Run one Memanto CLI step and return sanitized combined output."""
    result = subprocess.run(  # noqa: S603
        argv,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    output = _clean_output(
        "\n".join(part for part in (result.stdout, result.stderr) if part),
        private_roots,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {Path(argv[0]).name} "
            f"{' '.join(argv[1:4])}\n{output}"
        )
    return output


def _load_live_questions(path: Path) -> list[dict[str, Any]]:
    """Load questions with explicit terms expected in live recall output."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = raw.get("questions") if isinstance(raw, dict) else None
    if not isinstance(questions, list) or not questions:
        raise ValueError("Golden question file must contain a questions list")
    for index, question in enumerate(questions):
        terms = question.get("live_must_contain")
        if not isinstance(terms, list) or not terms:
            raise ValueError(f"questions[{index}].live_must_contain is required")
    return questions


def _recall_until_indexed(
    *,
    questions: list[dict[str, Any]],
    attempts: int,
    delay_seconds: float,
    env: dict[str, str],
    private_roots: list[Path],
) -> list[dict[str, Any]]:
    """Retry eventual-consistency recall and require every expected live term."""
    base = [sys.executable, "-m", "memanto"]
    results: list[dict[str, Any]] = []
    for question in questions:
        query = str(question["question"])
        terms = [str(value) for value in question["live_must_contain"]]
        matched_attempt: int | None = None
        for attempt in range(1, attempts + 1):
            output = _run(
                [*base, "recall", query, "--limit", "3"],
                env=env,
                private_roots=private_roots,
            )
            if all(term.casefold() in output.casefold() for term in terms):
                matched_attempt = attempt
                break
            if attempt < attempts:
                time.sleep(delay_seconds)
        if matched_attempt is None:
            raise RuntimeError(
                f"Live recall failed for {question.get('id')} after {attempts} attempts"
            )
        results.append(
            {
                "id": question.get("id"),
                "query": query,
                "matched_terms": terms,
                "attempt": matched_attempt,
                "passed": True,
            }
        )
    return results


def _validate_exported_bundle(
    export_path: Path, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Require three exported memories and every expected fact in Markdown."""
    loaded = load_okf_bundle(export_path)
    memories = loaded["memories"]
    searchable = "\n".join(
        f"{memory.get('title', '')}\n{memory.get('body', '')}" for memory in memories
    )
    missing: list[str] = []
    for question in questions:
        for term in question["live_must_contain"]:
            if str(term).casefold() not in searchable.casefold():
                missing.append(f"{question.get('id')}: {term}")
    return {
        "memory_count": len(memories),
        "expected_memory_count": len(questions),
        "all_expected_facts_present": not missing,
        "missing": missing,
        "valid": len(memories) == len(questions) and not missing,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    """Write sanitized validation evidence as deterministic UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    )


def _parser() -> argparse.ArgumentParser:
    """Build the guarded live-demo command-line parser."""
    parser = argparse.ArgumentParser(
        description="Run the live Memanto import -> recall -> OKF export loop."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--agent", default="n8n-operations")
    parser.add_argument("--reuse-agent", action="store_true")
    parser.add_argument("--activation-hours", type=int, default=6)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    parser.add_argument("--bundle", type=Path, default=HERE / "sample-okf")
    parser.add_argument(
        "--questions",
        type=Path,
        default=HERE / "golden-questions.yaml",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=HERE / "live-roundtrip-okf",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=HERE / "live-validation.json",
    )
    return parser


def main() -> int:
    """Execute the guarded freedom loop or print its secret-free plan."""
    args = _parser().parse_args()
    if args.activation_hours < 1 or args.attempts < 1 or args.delay_seconds < 0:
        raise SystemExit(
            "activation hours/attempts must be positive; delay cannot be negative"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    memanto_root = (Path.home() / ".memanto").resolve()
    export_path = memanto_root / "exports" / f"{args.agent}-roundtrip-{stamp}"
    bundle = args.bundle.resolve()
    evidence_dir = args.evidence_dir.resolve()
    report_path = args.report.resolve()
    questions = _load_live_questions(args.questions.resolve())
    plan = build_command_plan(
        args.agent,
        bundle,
        export_path,
        reuse_agent=args.reuse_agent,
        activation_hours=args.activation_hours,
    )

    if not args.execute:
        print(
            json.dumps(
                {
                    "execute": False,
                    "note": "Add --execute after reviewing this secret-free plan.",
                    "agent": args.agent,
                    "steps": plan,
                    "questions": [row["id"] for row in questions],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if len(api_key) < 20 or any(character.isspace() for character in api_key):
        raise SystemExit("MOORCHEH_API_KEY is missing or malformed")
    if evidence_dir.exists():
        raise SystemExit(f"Refusing to overwrite evidence directory: {evidence_dir}")
    if export_path.exists():
        raise SystemExit(f"Refusing to overwrite staged export: {export_path}")

    env = os.environ.copy()
    env["MOORCHEH_API_KEY"] = api_key
    env["COLUMNS"] = "240"
    private_roots = [Path.home(), HERE.parents[2]]

    activation_output = _run(plan[0]["argv"], env=env, private_roots=private_roots)
    import_output = _run(plan[1]["argv"], env=env, private_roots=private_roots)
    import_match = re.search(r"Imported:\s*(\d+)\s+Failed:\s*(\d+)", import_output)
    if not import_match or import_match.groups() != ("3", "0"):
        raise RuntimeError("Live import did not report Imported: 3 / Failed: 0")

    recalls = _recall_until_indexed(
        questions=questions,
        attempts=args.attempts,
        delay_seconds=args.delay_seconds,
        env=env,
        private_roots=private_roots,
    )
    export_output = _run(plan[2]["argv"], env=env, private_roots=private_roots)
    export_match = re.search(r"Exported\s+(\d+)\s+memories", export_output)
    if not export_match or export_match.group(1) != "3":
        raise RuntimeError("Live export did not report 3 memories")

    validation = _validate_exported_bundle(export_path, questions)
    if not validation["valid"]:
        raise RuntimeError("Exported live OKF bundle failed factual validation")
    shutil.copytree(export_path, evidence_dir)

    report = {
        "version": 1,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "agent": args.agent,
        "namespace": f"memanto_agent_{args.agent}",
        "source_bundle": bundle.name,
        "activation": {
            "mode": "reuse" if args.reuse_agent else "create",
            "passed": bool(activation_output),
        },
        "import": {"imported": 3, "failed": 0, "passed": True},
        "recall": {
            "passed": len(recalls),
            "questions": len(questions),
            "results": recalls,
        },
        "export": {
            "exported": 3,
            "evidence_dir": evidence_dir.name,
            **validation,
        },
        "valid": True,
    }
    _write_report(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

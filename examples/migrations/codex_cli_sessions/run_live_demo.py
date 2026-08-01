#!/usr/bin/env python3
"""Run and record the live OKF -> Memanto -> portable OKF freedom loop.

The script deliberately shells out to Memanto's shipped CLI so the transcript
is evidence of the same public commands a user runs. It never reads or prints
the Moorcheh key; the key is inherited by child processes from the environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Build the live-demo command-line parser."""
    example_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=example_dir / "sample_okf")
    parser.add_argument(
        "--golden",
        type=Path,
        help="golden Q&A JSON (defaults to <bundle>/golden_questions.json)",
    )
    parser.add_argument(
        "--agent",
        help="new Memanto agent id (defaults to a timestamped demo id)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("codex-okf-live-evidence"),
        help="new directory for transcript, report, and exported OKF",
    )
    parser.add_argument(
        "--answer-count",
        type=int,
        default=5,
        help="number of golden questions to answer with RAG after import",
    )
    parser.add_argument(
        "--memanto-bin",
        help="Memanto executable (defaults to the executable on PATH)",
    )
    return parser


def _utc_now() -> str:
    """Return the current UTC time in an ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_golden_cases(path: Path, bundle: Path) -> list[dict[str, str]]:
    """Load questions and derive the exact OKF title each must retrieve."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("questions", [])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    record_by_source = {
        str(record.get("source_record_sha256") or ""): str(
            record.get("entry_id") or ""
        )
        for record in manifest.get("records", [])
        if isinstance(record, dict)
    }
    cases: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        source_hash = str(item.get("expected_source_record_sha256") or "").strip()
        entry_id = record_by_source.get(source_hash, "")
        if not question or not entry_id:
            continue
        matches = list((bundle / "memories").rglob(f"*{entry_id}*.md"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one OKF memory for golden source {source_hash}, "
                f"found {len(matches)}"
            )
        text = matches[0].read_text(encoding="utf-8")
        title_match = re.search(r'^title:\s*["\'](?P<title>.*?)["\']\s*$', text, re.M)
        if not title_match:
            raise ValueError(f"OKF memory has no quoted title: {matches[0]}")
        cases.append(
            {
                "id": str(item.get("id") or entry_id),
                "question": question,
                "expected_title": title_match.group("title"),
            }
        )
    if not cases:
        raise ValueError(f"golden Q&A has no questions: {path}")
    return cases


def build_command_plan(
    *,
    memanto_bin: str,
    agent_id: str,
    bundle: Path,
    portable_output: Path,
    questions: Sequence[str],
    answer_count: int,
) -> list[tuple[str, list[str]]]:
    """Build the exact shipped-CLI command sequence for the freedom loop."""
    plan: list[tuple[str, list[str]]] = [
        (
            "create_empty_agent",
            [
                memanto_bin,
                "agent",
                "create",
                agent_id,
                "--pattern",
                "project",
                "--description",
                "Live Codex CLI to OKF portability proof",
            ],
        )
    ]
    for index, question in enumerate(questions, start=1):
        plan.append(
            (
                f"before_recall_{index}",
                [memanto_bin, "recall", question, "--limit", "1"],
            )
        )
    plan.append(
        (
            "import_okf",
            [memanto_bin, "migrate", "okf", str(bundle), "--agent", agent_id],
        )
    )
    for index, question in enumerate(questions, start=1):
        plan.append(
            (
                f"after_recall_{index}",
                [memanto_bin, "recall", question, "--limit", "1"],
            )
        )
    for index, question in enumerate(questions[: max(answer_count, 0)], start=1):
        plan.append(
            (
                f"after_answer_{index}",
                [memanto_bin, "answer", question, "--limit", "3"],
            )
        )
    plan.append(
        (
            "export_portable_okf",
            [
                memanto_bin,
                "memory",
                "export",
                "--agent",
                agent_id,
                "--output",
                str(portable_output),
                "--limit",
                "100",
                "--okf",
            ],
        )
    )
    return plan


def _public_command(command: Sequence[str]) -> str:
    """Format a command without exposing the executable's local absolute path."""
    public = ["memanto", *command[1:]]
    return shlex.join(public)


def _sanitize_output(text: str) -> str:
    """Remove machine-specific home and working-directory paths from evidence."""
    sanitized = text
    replacements = (
        (str(Path.cwd()), "."),
        (str(Path.home()), "$HOME"),
    )
    for private_path, public_path in replacements:
        sanitized = re.sub(
            re.escape(private_path), public_path, sanitized, flags=re.IGNORECASE
        )
    return sanitized


def _run_command(
    label: str,
    command: Sequence[str],
    *,
    transcript: Any,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Stream one command to screen and transcript, returning safe metadata."""
    display = _public_command(command)
    heading = f"\n=== {label} ===\n$ {display}\n"
    print(heading, end="", flush=True)
    transcript.write(heading)
    started = time.perf_counter()
    digest = hashlib.sha256()
    captured_output: list[str] = []
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert process.stdout is not None
    for line in process.stdout:
        safe_line = _sanitize_output(line)
        print(safe_line, end="", flush=True)
        transcript.write(safe_line)
        digest.update(safe_line.encode("utf-8"))
        captured_output.append(safe_line)
    return_code = process.wait()
    elapsed = time.perf_counter() - started
    transcript.flush()
    result = {
        "label": label,
        "command": display,
        "return_code": return_code,
        "elapsed_seconds": round(elapsed, 3),
        "stdout_sha256": digest.hexdigest(),
        # Kept only in memory for semantic verification and removed before the
        # public JSON report is written; the full safe output stays in the
        # transcript where a reviewer can inspect it.
        "_stdout": "".join(captured_output),
    }
    if return_code:
        raise RuntimeError(f"{label} failed with exit code {return_code}")
    return result


def verify_live_results(
    results: Sequence[dict[str, Any]],
    cases: Sequence[dict[str, str]],
    answer_count: int,
) -> dict[str, Any]:
    """Prove the fresh agent was empty and each query retrieved its exact title."""
    by_label = {str(item["label"]): item for item in results}
    checks: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        before = str(by_label[f"before_recall_{index}"].get("_stdout") or "")
        after = str(by_label[f"after_recall_{index}"].get("_stdout") or "")
        title = case["expected_title"]
        row: dict[str, Any] = {
            "id": case["id"],
            "before_import_empty": "No memories found" in before,
            "after_import_exact_title_recalled": title in after,
        }
        if index <= max(answer_count, 0):
            answer = str(by_label[f"after_answer_{index}"].get("_stdout") or "")
            row["rag_context_includes_exact_title"] = title in answer
        checks.append(row)
    verified = all(
        row["before_import_empty"]
        and row["after_import_exact_title_recalled"]
        and row.get("rag_context_includes_exact_title", True)
        for row in checks
    )
    return {
        "verified": verified,
        "checks": checks,
        "recall_passed": sum(
            bool(row["after_import_exact_title_recalled"]) for row in checks
        ),
        "recall_total": len(checks),
        "rag_context_passed": sum(
            bool(row.get("rag_context_includes_exact_title"))
            for row in checks
            if "rag_context_includes_exact_title" in row
        ),
        "rag_context_total": sum(
            "rag_context_includes_exact_title" in row for row in checks
        ),
    }


def _file_manifest(root: Path) -> list[dict[str, Any]]:
    """Return hashes and sizes for every file in a portable OKF export."""
    if not root.is_dir():
        raise FileNotFoundError(f"portable OKF export was not created: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        content = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the live proof and persist a secret-free evidence package."""
    args = build_parser().parse_args(argv)
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("error: MOORCHEH_API_KEY is not set", file=sys.stderr)
        return 2
    memanto_bin = args.memanto_bin or shutil.which("memanto")
    if not memanto_bin:
        print("error: memanto executable not found on PATH", file=sys.stderr)
        return 2
    bundle = args.bundle.resolve()
    golden = (args.golden or bundle / "golden_questions.json").resolve()
    output = args.output.resolve()
    if output.exists():
        print(f"error: output already exists: {output}", file=sys.stderr)
        return 2
    agent_id = args.agent or datetime.now(timezone.utc).strftime(
        "codex-okf-live-%Y%m%d%H%M%S"
    )
    try:
        cases = _load_golden_cases(golden, bundle)
        questions = [case["question"] for case in cases]
        output.mkdir(parents=True)
        portable_output = output / "portable_okf"
        bundle_cli = Path(os.path.relpath(bundle, Path.cwd()))
        portable_output_cli = Path(os.path.relpath(portable_output, Path.cwd()))
        plan = build_command_plan(
            memanto_bin=memanto_bin,
            agent_id=agent_id,
            bundle=bundle_cli,
            portable_output=portable_output_cli,
            questions=questions,
            answer_count=args.answer_count,
        )
        environment = dict(os.environ)
        environment.update({"DEBUG": "false", "NO_COLOR": "1", "PYTHONUTF8": "1"})
        results: list[dict[str, Any]] = []
        transcript_path = output / "live_transcript.txt"
        started_at = _utc_now()
        with transcript_path.open("w", encoding="utf-8", newline="\n") as transcript:
            for label, command in plan:
                results.append(
                    _run_command(
                        label,
                        command,
                        transcript=transcript,
                        environment=environment,
                    )
                )
        verification = verify_live_results(results, cases, args.answer_count)
        public_results = []
        for result in results:
            public_result = dict(result)
            public_result.pop("_stdout", None)
            public_results.append(public_result)
        report = {
            "schema_version": "1.0",
            "started_at": started_at,
            "completed_at": _utc_now(),
            "agent_id": agent_id,
            "source_bundle_manifest_sha256": hashlib.sha256(
                (bundle / "manifest.json").read_bytes()
            ).hexdigest(),
            "golden_questions": len(questions),
            "rag_answers_requested": min(max(args.answer_count, 0), len(questions)),
            "commands": public_results,
            "verification": verification,
            "portable_okf_files": _file_manifest(portable_output),
            "secrets_persisted": False,
        }
        (output / "live_demo_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if verification["verified"]:
            print(f"\nPASS: live evidence written to {args.output}")
            return 0
        print(
            f"\nFAIL: live commands completed but semantic checks failed; "
            f"evidence written to {args.output}",
            file=sys.stderr,
        )
        return 1
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

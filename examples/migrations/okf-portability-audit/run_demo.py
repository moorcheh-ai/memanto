"""Run the real-data OKF portability showcase with one command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _display_command(command: list[str]) -> str:
    """Render a concise command without machine-specific Python paths."""
    displayed = command.copy()
    if displayed and Path(displayed[0]).resolve() == Path(sys.executable).resolve():
        displayed[0] = "python"
        if len(displayed) > 1 and displayed[1].endswith(".py"):
            displayed[1] = Path(displayed[1]).name
    return " ".join(displayed)


def _run(
    command: list[str], *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run one visible, reproducible pipeline step and fail immediately on error."""
    print(f"\n$ {_display_command(command)}", flush=True)
    return subprocess.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
    )


def run_showcase(
    repository: str,
    issue: int,
    workdir: Path,
    max_comments: int | None = None,
    show_report: bool = False,
) -> dict[str, Any]:
    """Generate, dry-run, round-trip, and audit one genuine GitHub archive."""
    if workdir.exists():
        raise FileExistsError(f"Work directory must be new: {workdir}")
    workdir.mkdir(parents=True)

    root = Path(__file__).resolve().parent
    source = workdir / "github-memory"
    target = workdir / "round-tripped"
    report_path = workdir / "audit.json"
    generator = root / "github_issue_to_okf.py"
    roundtrip = root / "roundtrip_demo.py"
    audit = root / "okf_audit.py"

    started = time.perf_counter()
    generator_command = [
        sys.executable,
        str(generator),
        repository,
        str(issue),
        str(source),
    ]
    if max_comments is not None:
        generator_command.extend(["--max-comments", str(max_comments)])
    _run(generator_command)

    _run(["memanto", "migrate", "okf", str(source), "--dry-run"])
    _run([sys.executable, str(roundtrip), str(source), str(target)])
    audit_command = [
        sys.executable,
        str(audit),
        str(source),
        str(target),
        "--format",
        "json",
        "--fail-on-change",
    ]
    audit_error: subprocess.CalledProcessError | None = None
    try:
        audit_stdout = _run(audit_command, capture=True).stdout
    except subprocess.CalledProcessError as error:
        audit_error = error
        if isinstance(error.stdout, bytes):
            audit_stdout = error.stdout.decode("utf-8")
        else:
            audit_stdout = error.stdout or ""
    if show_report:
        print(audit_stdout, end="", flush=True)
    report = json.loads(audit_stdout)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if audit_error is not None:
        raise audit_error

    elapsed = round(time.perf_counter() - started, 2)
    summary = {
        "repository": repository,
        "issue": issue,
        "source_records": report["source_count"],
        "target_records": report["target_count"],
        "unchanged": report["unchanged"],
        "removed": len(report["removed"]),
        "changed": len(report["changed"]),
        "is_lossless": report["is_lossless"],
        "elapsed_seconds": elapsed,
        "report": str(report_path.resolve()),
    }
    print("\nSHOWCASE SUMMARY", flush=True)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    """Build the one-command showcase parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="moorcheh-ai/memanto")
    parser.add_argument("--issue", type=int, default=1609)
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="New output directory (defaults to a temporary directory)",
    )
    parser.add_argument("--max-comments", type=int, default=None)
    parser.add_argument(
        "--show-report",
        action="store_true",
        help="Print the complete audit JSON in addition to the compact summary",
    )
    return parser


def main() -> int:
    """Run the command-line showcase."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    if args.workdir is None:
        temp_root = Path(tempfile.mkdtemp(prefix="memanto-showcase-"))
        workdir = temp_root / "output"
    else:
        workdir = args.workdir
    run_showcase(
        args.repository,
        args.issue,
        workdir,
        args.max_comments,
        args.show_report,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

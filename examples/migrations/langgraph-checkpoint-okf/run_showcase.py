"""Run the full LangGraph checkpoint -> OKF migration showcase."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from generate_langgraph_checkpoint import generate_checkpoint
from langgraph_checkpoint_to_okf import convert
from validate_recall_parity import validate


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
SAMPLE_OUTPUT = ROOT / "sample_output"
SOURCE_DB = SAMPLE_OUTPUT / "source" / "langgraph_memory.sqlite"
TRANSCRIPT = SAMPLE_OUTPUT / "source" / "transcript.json"
OKF_DIR = SAMPLE_OUTPUT / "okf_bundle"
GOLDEN_QA = ROOT / "data" / "golden_qa.json"
VALIDATION_REPORT = SAMPLE_OUTPUT / "validation" / "recall-parity-report.md"
DRY_RUN_LOG = SAMPLE_OUTPUT / "memanto_migrate_okf_dry_run.txt"


def rel(path: Path, base: Path = ROOT) -> str:
    return path.relative_to(base).as_posix()


def sanitize_log(text: str) -> str:
    cleaned = text.replace("\\", "/")
    cleaned = cleaned.replace(str(REPO_ROOT).replace("\\", "/"), "<repo>")
    cleaned = cleaned.replace(str(Path.home()).replace("\\", "/"), "~")
    cleaned = re.sub(
        r"~/\.memanto/migrate/okf/\d{8}_\d{6}",
        "~/.memanto/migrate/okf/<run-id>",
        cleaned,
    )
    cleaned = cleaned.encode("ascii", errors="ignore").decode("ascii")
    return "\n".join(line.rstrip() for line in cleaned.splitlines())


def run_memanto_dry_run() -> dict:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    okf_arg = OKF_DIR.relative_to(REPO_ROOT).as_posix()
    cmd = [
        sys.executable,
        "-m",
        "memanto.cli.main",
        "migrate",
        "okf",
        okf_arg,
        "--dry-run",
    ]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        encoding="utf-8",
        errors="replace",
        text=True,
        capture_output=True,
        check=False,
    )
    display_cmd = ["python", "-m", *cmd[2:]]
    DRY_RUN_LOG.write_text(
        "COMMAND: "
        + " ".join(display_cmd)
        + "\n\nSTDOUT:\n"
        + sanitize_log(result.stdout)
        + "\n\nSTDERR:\n"
        + sanitize_log(result.stderr),
        encoding="utf-8",
    )
    return {"returncode": result.returncode, "log": rel(DRY_RUN_LOG)}


def require_full_parity(validation: dict) -> None:
    questions = validation.get("questions")
    parity_score = validation.get("parity_score")
    if not isinstance(questions, int) or questions <= 0:
        raise RuntimeError("Recall parity validation did not report a question count")
    if parity_score != questions:
        raise RuntimeError(
            "Recall parity validation failed: "
            f"{parity_score}/{questions} questions matched both source and OKF"
        )


def main() -> None:
    SAMPLE_OUTPUT.mkdir(parents=True, exist_ok=True)

    source_summary = generate_checkpoint(SOURCE_DB, TRANSCRIPT)
    source_summary["database"] = rel(SOURCE_DB)
    records = convert(SOURCE_DB, OKF_DIR, overwrite=True)
    validation = validate(SOURCE_DB, OKF_DIR, GOLDEN_QA, VALIDATION_REPORT)
    require_full_parity(validation)
    dry_run = run_memanto_dry_run()

    summary = {
        "source": source_summary,
        "okf_bundle": rel(OKF_DIR),
        "mapped_memories": len(records),
        "validation": validation,
        "memanto_migrate_okf_dry_run": dry_run,
    }
    SAMPLE_OUTPUT.joinpath("summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))

    if dry_run["returncode"] != 0:
        raise SystemExit(
            "memanto migrate okf --dry-run failed; see "
            f"{DRY_RUN_LOG.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()

"""Memory wrapper utilities for running agent skills with Memanto.

The module intentionally talks to Memanto through its CLI. That keeps the
example compatible with the same setup path users already follow when they run
``memanto`` from a terminal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


DEFAULT_AGENT_ID = os.getenv("MEMANTO_SKILL_AGENT_ID")
DEFAULT_RUN_DIR = Path(os.getenv("MEMANTO_SKILL_RUN_DIR", ".memanto-skill-runs"))
DEFAULT_CONTEXT_FILE = Path(
    os.getenv("MEMANTO_SKILL_CONTEXT_FILE", ".memanto-skill-context.md")
)


@dataclass
class SkillRun:
    """Captured metadata and output for one wrapped skill execution."""

    skill: str
    task: str
    command: list[str]
    cwd: str
    started_at: str
    finished_at: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    recalled_context: str = ""


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def run_process(command: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture text output without raising on failure."""

    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def memanto_command(
    args: Sequence[str],
    *,
    dry_run: bool,
) -> subprocess.CompletedProcess[str]:
    """Run a Memanto CLI command, or simulate success during dry-run mode."""

    if dry_run:
        return subprocess.CompletedProcess(["memanto", *args], 0, "", "")
    return run_process(["memanto", *args])


def build_recall_query(skill: str, task: str, cwd: Path) -> str:
    """Build a broad memory search query for the current skill and project."""

    project = cwd.name
    return (
        f"{project} {skill} {task} architecture decisions coding preferences "
        "known errors implementation constraints"
    )


def recall_context(
    *,
    agent_id: str | None,
    skill: str,
    task: str,
    cwd: Path,
    dry_run: bool,
) -> str:
    """Recall relevant Memanto memories to inject before a skill starts."""

    query = build_recall_query(skill, task, cwd)
    args = ["recall", query, "--limit", "12"]
    if agent_id:
        args.extend(["--agent", agent_id])

    result = memanto_command(args, dry_run=dry_run)
    if result.returncode != 0:
        return (
            "Memanto recall failed. Continue without injected memory.\n\n"
            f"stderr:\n{result.stderr.strip()}"
        )

    if dry_run:
        return f"Dry run recall query: {query}"

    return result.stdout.strip() or "No relevant Memanto memories found."


def write_context_file(path: Path, run: SkillRun) -> None:
    """Write recalled memories and usage guidance for the wrapped agent."""

    path.write_text(
        "\n".join(
            [
                "# Memanto Skill Context",
                "",
                f"Skill: {run.skill}",
                f"Task: {run.task}",
                f"Started: {run.started_at}",
                "",
                "## Recalled Memories",
                "",
                run.recalled_context,
                "",
                "## Instruction For The Agent",
                "",
                "Use the recalled memories as constraints when they are relevant. "
                "Prefer explicit project decisions, user preferences, and known "
                "errors over generic defaults.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def redact(text: str) -> str:
    """Remove common secret-looking values before storing transcript excerpts."""

    patterns = [
        r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+",
        r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+",
    ]
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    return redacted


def infer_summary(run: SkillRun) -> str:
    """Create a compact memory summary from the captured skill transcript."""

    transcript = "\n".join([run.stdout, run.stderr])
    cleaned = redact(transcript)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    interesting = [
        line
        for line in lines
        if re.search(
            r"(?i)\b(error|failed|fixed|implemented|decision|todo|test|passing|"
            r"regression|architecture|created|updated)\b",
            line,
        )
    ]
    excerpt = interesting[:12] or lines[:12]
    if not excerpt:
        excerpt = ["No command output was captured."]

    status = "succeeded" if run.exit_code == 0 else f"exited with {run.exit_code}"
    return "\n".join(
        [
            f"Skill `{run.skill}` {status} for task: {run.task}",
            "",
            "Captured notes:",
            *[f"- {line[:240]}" for line in excerpt],
        ]
    )


def memory_type_for_run(run: SkillRun) -> str:
    """Choose a Memanto memory type that matches the run outcome and skill."""

    if run.exit_code and run.exit_code != 0:
        return "error"
    lowered = f"{run.skill} {run.task}".lower()
    if "grill" in lowered or "architecture" in lowered:
        return "decision"
    if "handoff" in lowered:
        return "context"
    return "learning"


def store_summary(
    *,
    run: SkillRun,
    agent_id: str | None,
    dry_run: bool,
) -> subprocess.CompletedProcess[str]:
    """Store the inferred post-run summary back into Memanto."""

    summary = infer_summary(run)
    tags = ",".join(
        tag
        for tag in [
            "skill-memory",
            run.skill.lower().replace("/", "").replace(" ", "-"),
            Path(run.cwd).name.lower(),
        ]
        if tag
    )
    args = [
        "remember",
        summary,
        "--type",
        memory_type_for_run(run),
        "--confidence",
        "0.85",
        "--provenance",
        "observed",
        "--source",
        "claudecode_skills_memanto",
        "--tags",
        tags,
    ]
    if agent_id:
        args.extend(["--agent", agent_id])
    return memanto_command(args, dry_run=dry_run)


def write_transcript(run_dir: Path, run: SkillRun) -> Path:
    """Persist the complete run record as a local JSON transcript."""

    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = run.started_at.replace(":", "").replace("+", "Z")
    safe_skill = re.sub(r"[^A-Za-z0-9_.-]+", "-", run.skill).strip("-")
    path = run_dir / f"{stamp}-{safe_skill}.json"
    path.write_text(json.dumps(asdict(run), indent=2), encoding="utf-8")
    return path


def execute_skill_with_memory(
    *,
    skill: str,
    task: str,
    command: Sequence[str],
    agent_id: str | None = DEFAULT_AGENT_ID,
    cwd: Path | None = None,
    run_dir: Path = DEFAULT_RUN_DIR,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    dry_run: bool = False,
) -> tuple[SkillRun, Path, subprocess.CompletedProcess[str]]:
    """Execute a command with pre-run recall and post-run memory writeback."""

    cwd = (cwd or Path.cwd()).resolve()
    run = SkillRun(
        skill=skill,
        task=task,
        command=list(command),
        cwd=str(cwd),
        started_at=utc_now(),
    )
    run.recalled_context = recall_context(
        agent_id=agent_id,
        skill=skill,
        task=task,
        cwd=cwd,
        dry_run=dry_run,
    )
    write_context_file(context_file, run)

    if dry_run:
        result = subprocess.CompletedProcess(list(command), 0, "dry run\n", "")
    else:
        result = run_process(command, cwd=cwd)

    run.finished_at = utc_now()
    run.exit_code = result.returncode
    run.stdout = result.stdout
    run.stderr = result.stderr

    transcript_path = write_transcript(run_dir, run)
    remember_result = store_summary(run=run, agent_id=agent_id, dry_run=dry_run)
    return run, transcript_path, remember_result


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the example wrapper."""

    parser = argparse.ArgumentParser(
        description="Run an agent skill command with Memanto recall and writeback."
    )
    parser.add_argument("--skill", required=True, help="Skill name, e.g. tdd")
    parser.add_argument("--task", required=True, help="Human-readable task summary")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--context-file", type=Path, default=DEFAULT_CONTEXT_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for running a skill command with Memanto memory hooks."""

    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("provide the skill command after --")

    run, transcript_path, remember_result = execute_skill_with_memory(
        skill=args.skill,
        task=args.task,
        command=command,
        agent_id=args.agent_id,
        run_dir=args.run_dir,
        context_file=args.context_file,
        dry_run=args.dry_run,
    )

    print(f"context_file={args.context_file}")
    print(f"transcript={transcript_path}")
    print(f"exit_code={run.exit_code}")
    if remember_result.returncode != 0:
        print("memanto_remember=failed")
        print(remember_result.stderr)
    else:
        print("memanto_remember=ok")

    if run.stdout:
        print(run.stdout, end="")
    if run.stderr:
        print(run.stderr, end="")
    return int(run.exit_code or 0)


if __name__ == "__main__":
    raise SystemExit(main())

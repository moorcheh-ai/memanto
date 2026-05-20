#!/usr/bin/env python3
"""Bridge Claude Code skill runs with Memanto long-term memory.

The script is intentionally a thin CLI wrapper around the existing `memanto`
command. It can be used in dry-run mode for demos and tests, or against a real
Memanto agent when MOORCHEH_API_KEY is configured.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AGENT_ID = "claudecode-skills"
MEMORY_BLOCK_START = "<memanto-engineering-memory>"
MEMORY_BLOCK_END = "</memanto-engineering-memory>"

SECRET_PATTERNS = [
    re.compile(r"mch_[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9]{12,}"),
]


@dataclass(frozen=True)
class MemoryPayload:
    """A memory that should be stored after a skill run."""

    content: str
    memory_type: str
    title: str
    tags: tuple[str, ...]


def redact_secrets(text: str) -> str:
    """Remove common API-token shapes before persisting transcripts."""

    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def build_recall_query(skill_name: str, task: str, path: str | None) -> str:
    """Build a concise retrieval query for memories relevant to a skill run."""

    path_hint = f" Path: {path}." if path else ""
    return (
        f"Engineering decisions, codebase quirks, and preferences relevant to "
        f"Claude Code skill '{skill_name}' for task: {task}.{path_hint}"
    )


def format_memory_block(memories: str) -> str:
    """Render recalled memories as a prompt-ready constraint block."""

    stripped = memories.strip()
    if not stripped:
        stripped = "- No prior Memanto memories matched this task."
    return f"{MEMORY_BLOCK_START}\n{stripped}\n{MEMORY_BLOCK_END}"


def extract_memory_candidates(
    *,
    skill_name: str,
    task: str,
    transcript: str,
    path: str | None = None,
) -> list[MemoryPayload]:
    """Distill a skill transcript into durable engineering memories."""

    safe_transcript = redact_secrets(transcript)
    meaningful_lines = [
        re.sub(r"^[-* >\t]+", "", line).rstrip()
        for line in safe_transcript.splitlines()
        if line.strip()
    ]
    signal_lines = [
        line
        for line in meaningful_lines
        if re.search(
            r"\b(decision|decide|preference|prefer|quirk|must|should|avoid|"
            r"convention|constraint|rule|test|architecture)\b",
            line,
            flags=re.IGNORECASE,
        )
    ]
    if not signal_lines:
        signal_lines = meaningful_lines[:8]

    summary = "\n".join(f"- {line}" for line in signal_lines[:12])
    location = f"\nRelated path: {path}" if path else ""
    base_tags = ("claude-code-skills", skill_name)

    return [
        MemoryPayload(
            title=f"{skill_name}: task outcome",
            memory_type="artifact",
            tags=base_tags + ("task-outcome",),
            content=(
                f"Skill '{skill_name}' completed task: {task}.{location}\n"
                f"Distilled outcome:\n{summary}"
            ),
        ),
        MemoryPayload(
            title=f"{skill_name}: reusable engineering constraints",
            memory_type="decision",
            tags=base_tags + ("engineering-profile",),
            content=(
                "Reusable engineering constraints discovered during the skill "
                f"run for '{task}':\n{summary}"
            ),
        ),
    ]


def run_process(args: Sequence[str], *, input_text: str | None = None) -> str:
    """Run a subprocess and return combined stdout/stderr text."""

    completed = subprocess.run(
        list(args),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: "
            f"{' '.join(args)}\n{output}"
        )
    return output


def memanto_command(explicit_path: str | None = None) -> list[str]:
    """Resolve the memanto command."""

    if explicit_path:
        return [explicit_path]
    found = shutil.which("memanto")
    if found:
        return [found]
    return [sys.executable, "-m", "memanto"]


def ensure_agent(agent_id: str, memanto: Sequence[str], dry_run: bool) -> None:
    """Activate the target agent, creating it if necessary."""

    if dry_run:
        return

    try:
        run_process([*memanto, "agent", "activate", agent_id])
    except RuntimeError:
        run_process(
            [
                *memanto,
                "agent",
                "create",
                agent_id,
                "--pattern",
                "project",
                "--description",
                "Shared memory for Claude Code skill executions",
            ]
        )


def recall_memories(
    *,
    skill_name: str,
    task: str,
    path: str | None,
    agent_id: str,
    memanto: Sequence[str],
    dry_run: bool,
) -> str:
    """Recall relevant memories and format them for prompt injection."""

    query = build_recall_query(skill_name, task, path)
    if dry_run:
        memories = (
            "- Prefer small vertical slices with tests before implementation.\n"
            "- Preserve repository naming conventions and existing helpers."
        )
        return format_memory_block(memories)

    ensure_agent(agent_id, memanto, dry_run=False)
    output = run_process([*memanto, "recall", query])
    return format_memory_block(output)


def store_memories(
    *,
    payloads: Sequence[MemoryPayload],
    agent_id: str,
    memanto: Sequence[str],
    dry_run: bool,
) -> str:
    """Store distilled memories and return a compact report."""

    if dry_run:
        return "\n".join(
            f"[dry-run] {payload.memory_type}: {payload.title}\n{payload.content}"
            for payload in payloads
        )

    ensure_agent(agent_id, memanto, dry_run=False)
    reports: list[str] = []
    for payload in payloads:
        output = run_process(
            [
                *memanto,
                "remember",
                payload.content,
                "--type",
                payload.memory_type,
                "--title",
                payload.title,
                "--tags",
                ",".join(payload.tags),
                "--source",
                "claude-code-skill-hook",
                "--provenance",
                "observed",
            ]
        )
        reports.append(output.strip())
    return "\n\n".join(reports)


def read_transcript(path: str | None, inline_summary: str | None) -> str:
    """Load a transcript from a file or direct summary text."""

    chunks: list[str] = []
    if path:
        chunks.append(Path(path).read_text(encoding="utf-8"))
    if inline_summary:
        chunks.append(inline_summary)
    if not chunks:
        raise ValueError("Provide --transcript-file, --summary, or use the run command.")
    return "\n\n".join(chunks)


def normalize_wrapped_command(command: Sequence[str]) -> list[str]:
    """Drop argparse's optional ``--`` separator before command execution."""

    normalized = list(command)
    if normalized and normalized[0] == "--":
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("Provide a command after --, for example: -- pytest -q")
    return normalized


def command_before(args: argparse.Namespace) -> int:
    """Handle the ``before`` subcommand by printing recalled memories."""

    block = recall_memories(
        skill_name=args.skill_name,
        task=args.task,
        path=args.path,
        agent_id=args.agent_id,
        memanto=memanto_command(args.memanto_bin),
        dry_run=args.dry_run,
    )
    print(block)
    return 0


def command_after(args: argparse.Namespace) -> int:
    """Handle the ``after`` subcommand by storing transcript-derived memories."""

    transcript = read_transcript(args.transcript_file, args.summary)
    payloads = extract_memory_candidates(
        skill_name=args.skill_name,
        task=args.task,
        transcript=transcript,
        path=args.path,
    )
    print(
        store_memories(
            payloads=payloads,
            agent_id=args.agent_id,
            memanto=memanto_command(args.memanto_bin),
            dry_run=args.dry_run,
        )
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    """Run a wrapped command between memory recall and memory writeback."""

    command = normalize_wrapped_command(args.command)

    context_block = recall_memories(
        skill_name=args.skill_name,
        task=args.task,
        path=args.path,
        agent_id=args.agent_id,
        memanto=memanto_command(args.memanto_bin),
        dry_run=args.dry_run,
    )
    print(context_block)
    print("\n--- skill command output ---")

    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    command_output_raw = "\n".join(
        part for part in [completed.stdout, completed.stderr] if part
    )
    command_output = redact_secrets(command_output_raw)
    print(command_output)

    payloads = extract_memory_candidates(
        skill_name=args.skill_name,
        task=args.task,
        transcript=command_output_raw,
        path=args.path,
    )
    print("\n--- memanto writeback ---")
    print(
        store_memories(
            payloads=payloads,
            agent_id=args.agent_id,
            memanto=memanto_command(args.memanto_bin),
            dry_run=args.dry_run,
        )
    )
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description="Memanto memory hook for Claude Code skill executions."
    )
    parser.add_argument(
        "--memanto-bin",
        default=os.environ.get("MEMANTO_BIN"),
        help="Path to the memanto executable. Defaults to PATH or python -m memanto.",
    )

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        """Attach common skill metadata options to a subcommand."""

        subparser.add_argument("--skill-name", required=True)
        subparser.add_argument("--task", required=True)
        subparser.add_argument("--path")
        subparser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
        subparser.add_argument("--dry-run", action="store_true")

    before = subparsers.add_parser("before", help="Recall memories before a skill.")
    add_common(before)
    before.set_defaults(func=command_before)

    after = subparsers.add_parser("after", help="Store memories after a skill.")
    add_common(after)
    after.add_argument("--transcript-file")
    after.add_argument("--summary")
    after.set_defaults(func=command_after)

    run = subparsers.add_parser("run", help="Wrap a command with recall/writeback.")
    add_common(run)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected subcommand."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

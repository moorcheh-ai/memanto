#!/usr/bin/env python3
"""Bridge Claude Code-style skill runs through Memanto memory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


DEFAULT_LIMIT = 5


class MemoryBackend(Protocol):
    """Minimal backend used by the hook so tests can avoid network calls."""

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        """Return relevant memories for the next skill run."""

    def remember(
        self,
        content: str,
        memory_type: str,
        title: str,
        tags: list[str],
        confidence: float,
    ) -> None:
        """Persist one memory."""


@dataclass(frozen=True)
class SkillRun:
    """Context passed to a skill invocation."""

    skill: str
    task: str
    files: tuple[str, ...] = ()
    transcript: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def query(self) -> str:
        file_hint = " ".join(self.files)
        return f"{self.skill} {self.task} {file_hint}".strip()


class MemantoCliBackend:
    """Backend that delegates to the existing ``memanto`` CLI."""

    def __init__(self, executable: str = "memanto") -> None:
        self.executable = executable

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        completed = subprocess.run(
            [
                self.executable,
                "recall",
                query,
                "--limit",
                str(limit),
                "--type",
                "decision",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return []
        return _extract_cli_memory_lines(completed.stdout)

    def remember(
        self,
        content: str,
        memory_type: str,
        title: str,
        tags: list[str],
        confidence: float,
    ) -> None:
        args = [
            self.executable,
            "remember",
            content,
            "--type",
            memory_type,
            "--title",
            title,
            "--source",
            "claudecode-skills-memanto",
            "--provenance",
            "inferred",
            "--confidence",
            f"{confidence:.2f}",
        ]
        if tags:
            args.extend(["--tags", ",".join(tags)])
        subprocess.run(args, check=True)


def _extract_cli_memory_lines(output: str) -> list[str]:
    """Keep the useful text from rich CLI output without depending on styling."""
    lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Found ", "ID:", "Type:", "Completed ")):
            continue
        if "Memory " in line and "Score:" in line:
            continue
        lines.append(line)
    return lines[:DEFAULT_LIMIT]


def build_context_block(run: SkillRun, backend: MemoryBackend) -> str:
    """Return a compact system-context block for the next skill prompt."""
    memories = backend.recall(run.query, limit=DEFAULT_LIMIT)
    if not memories:
        return ""

    bullets = "\n".join(f"- {memory}" for memory in memories)
    return (
        "<memanto-engineering-memory>\n"
        "Relevant prior engineering decisions for this skill run:\n"
        f"{bullets}\n"
        "</memanto-engineering-memory>"
    )


def summarize_transcript(run: SkillRun) -> list[dict[str, object]]:
    """Extract durable engineering memories from a completed skill transcript."""
    transcript = _compact(run.transcript)
    if not transcript:
        return []

    tags = ["claude-code-skills", f"skill:{run.skill}"]
    tags.extend(f"file:{Path(path).name}" for path in run.files[:5])

    summary = (
        f"Skill `{run.skill}` handled task `{run.task}`. "
        f"Files in scope: {', '.join(run.files) or 'not specified'}. "
        f"Outcome and decisions: {transcript}"
    )
    return [
        {
            "content": summary,
            "memory_type": "decision",
            "title": f"{run.skill}: {run.task[:72]}",
            "tags": tags,
            "confidence": 0.78,
        }
    ]


def store_completed_run(run: SkillRun, backend: MemoryBackend) -> int:
    """Persist memories inferred from a finished skill run."""
    memories = summarize_transcript(run)
    for memory in memories:
        backend.remember(
            content=str(memory["content"]),
            memory_type=str(memory["memory_type"]),
            title=str(memory["title"]),
            tags=list(memory["tags"]),
            confidence=float(memory["confidence"]),
        )
    return len(memories)


def _compact(text: str, max_chars: int = 1200) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[: max_chars - 3]}..."


def _read_transcript(args: argparse.Namespace) -> str:
    if args.transcript:
        return args.transcript
    if args.transcript_file:
        return Path(args.transcript_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _build_run(args: argparse.Namespace) -> SkillRun:
    metadata = {}
    if args.metadata:
        metadata = json.loads(args.metadata)
    return SkillRun(
        skill=args.skill,
        task=args.task,
        files=tuple(args.file or ()),
        transcript=_read_transcript(args),
        metadata=metadata,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inject and write back Memanto memory around skill executions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("pre", "post"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--skill", required=True)
        command_parser.add_argument("--task", required=True)
        command_parser.add_argument("--file", action="append")
        command_parser.add_argument("--metadata")
        command_parser.add_argument("--transcript")
        command_parser.add_argument("--transcript-file")

    args = parser.parse_args(argv)
    backend = MemantoCliBackend(os.environ.get("MEMANTO_EXECUTABLE", "memanto"))
    run = _build_run(args)

    if args.command == "pre":
        context = build_context_block(run, backend)
        if context:
            print(context)
        return 0

    stored = store_completed_run(run, backend)
    print(f"stored_memories={stored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

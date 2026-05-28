#!/usr/bin/env python3
"""Memanto memory bridge for Claude Code skills.

This example wraps skill runs with two small lifecycle hooks:

* ``pre`` recalls relevant engineering memories before a skill starts.
* ``post`` distills a completed skill transcript and stores new decisions.

It shells out to the public ``memanto`` CLI so the example stays lightweight and
works with the package users already install from PyPI.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_AGENT_ID = "claudecode-skills"
DEFAULT_LIMIT = 5

MEMORY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("artifact", r"\b(created|updated|wrote|added|changed|removed)\b"),
    ("decision", r"\b(decided|decision|adr|choose|chosen|selected)\b"),
    ("preference", r"\b(prefer|preference|style|convention|always|never)\b"),
    ("instruction", r"\b(constraint|must|cannot|avoid|required|requirement)\b"),
    ("learning", r"\b(learned|because|root cause|lesson|insight)\b"),
)


@dataclass(frozen=True)
class MemoryCandidate:
    """A distilled memory ready to persist in Memanto."""

    content: str
    memory_type: str


class MemantoCommandError(RuntimeError):
    """Raised when the memanto CLI cannot complete a requested operation."""


class MemantoBridge:
    """Thin subprocess adapter around the memanto CLI."""

    def __init__(
        self,
        agent_id: str = DEFAULT_AGENT_ID,
        command: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.command = command or os.environ.get("MEMANTO_COMMAND", "memanto")
        self.dry_run = dry_run
        self._ready = False

    def _base_command(self) -> list[str]:
        if self.command == "python -m memanto":
            return [sys.executable, "-m", "memanto"]
        return shlex.split(self.command)

    def _run(self, args: list[str], input_text: str | None = None) -> str:
        command = [*self._base_command(), *args]

        if self.dry_run:
            print("$ " + " ".join(shlex.quote(part) for part in command))
            if input_text:
                print(input_text)
            return ""

        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise MemantoCommandError(details or f"command failed: {command}")
        return completed.stdout.strip()

    def ensure_agent(self) -> None:
        """Create and activate the shared skill memory agent if needed."""

        if self._ready:
            return

        try:
            self._run(
                [
                    "agent",
                    "create",
                    self.agent_id,
                    "--pattern",
                    "developer-productivity",
                    "--description",
                    "Shared memory for Claude Code skills.",
                ]
            )
        except MemantoCommandError as exc:
            # The CLI may report that the agent already exists. That is fine:
            # activating it below is idempotent from this example's perspective.
            if "already" not in str(exc).lower() and "exists" not in str(exc).lower():
                raise

        self._run(["agent", "activate", self.agent_id])
        self._ready = True

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> str:
        self.ensure_agent()
        return self._run(["recall", query, "--limit", str(limit)])

    def remember(
        self,
        candidate: MemoryCandidate,
        skill: str,
        project_path: str,
    ) -> None:
        self.ensure_agent()
        tags = ",".join(
            [
                "claude-code-skill",
                f"skill:{slugify(skill)}",
                f"project:{slugify(Path(project_path).name or 'root')}",
            ]
        )
        self._run(
            [
                "remember",
                candidate.content,
                "--type",
                candidate.memory_type,
                "--source",
                f"skill:{skill}",
                "--tags",
                tags,
                "--confidence",
                "0.86",
            ]
        )


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower())
    return value.strip("-") or "unknown"


def normalize_line(line: str) -> str:
    line = re.sub(r"^\s*[-*#>\d.)\[]+\s*", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def iter_logical_lines(text: str) -> list[str]:
    """Merge wrapped markdown bullets into single candidate lines."""

    logical_lines: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            logical_lines.append(" ".join(part.strip() for part in current))
            current.clear()

    for raw_line in text.splitlines():
        if not raw_line.strip():
            flush()
            continue

        starts_new_item = bool(re.match(r"^\s*(?:[-*]|\d+[.)]|#+)\s+", raw_line))
        if starts_new_item:
            flush()
            current.append(raw_line)
            continue

        if current:
            current.append(raw_line)
        else:
            current.append(raw_line)

    flush()
    return logical_lines


def detect_memory_type(line: str) -> str | None:
    lowered = line.lower()
    for memory_type, pattern in MEMORY_PATTERNS:
        if re.search(pattern, lowered):
            return memory_type
    return None


def distill_transcript(text: str, max_memories: int = 8) -> list[MemoryCandidate]:
    """Extract durable engineering memories from a transcript.

    This intentionally favors precision over recall. The goal is to avoid noisy
    memories while preserving decisions, constraints, preferences, and lessons.
    """

    candidates: list[MemoryCandidate] = []
    seen: set[str] = set()

    for raw_line in iter_logical_lines(text):
        line = normalize_line(raw_line)
        if not line or len(line) < 24 or len(line) > 420:
            continue

        memory_type = detect_memory_type(line)
        if not memory_type:
            continue

        dedupe_key = line.lower()
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        candidates.append(MemoryCandidate(content=line, memory_type=memory_type))

        if len(candidates) >= max_memories:
            break

    return candidates


def build_recall_query(skill: str, task: str, project_path: str) -> str:
    project_name = Path(project_path).name or "current project"
    return (
        f"Relevant engineering decisions, codebase conventions, constraints, "
        f"and preferences for running /{skill} on {project_name}. Task: {task}"
    )


def format_recall_block(skill: str, recalled: str) -> str:
    if not recalled.strip():
        return (
            "## Memanto Skill Memory\n\n"
            f"No prior memories were found for /{skill}. Continue normally.\n"
        )

    return (
        "## Memanto Skill Memory\n\n"
        "Use these recalled memories as system constraints for the next skill "
        "run. Prefer recent, project-specific memories when they conflict.\n\n"
        f"{recalled}\n"
    )


def command_pre(args: argparse.Namespace) -> int:
    bridge = MemantoBridge(args.agent, args.memanto_command, args.dry_run)
    query = build_recall_query(args.skill, args.task, args.project)
    recalled = bridge.recall(query, args.limit)
    print(format_recall_block(args.skill, recalled))
    return 0


def read_transcript(args: argparse.Namespace) -> str:
    if args.transcript:
        return Path(args.transcript).read_text(encoding="utf-8")
    if args.summary:
        return args.summary
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --transcript, --summary, or pipe transcript text.")


def command_post(args: argparse.Namespace) -> int:
    transcript = read_transcript(args)
    candidates = distill_transcript(transcript, args.max_memories)

    if not candidates:
        print("No durable engineering memories detected.")
        return 0

    bridge = MemantoBridge(args.agent, args.memanto_command, args.dry_run)
    for candidate in candidates:
        bridge.remember(candidate, args.skill, args.project)
        print(f"Stored {candidate.memory_type}: {candidate.content}")

    return 0


def command_demo(args: argparse.Namespace) -> int:
    transcript = Path(args.transcript).read_text(encoding="utf-8")
    print("Distilled memories:")
    for candidate in distill_transcript(transcript, args.max_memories):
        print(f"- {candidate.memory_type}: {candidate.content}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Memanto bridge for Claude Code skill memory."
    )
    parser.add_argument(
        "--agent",
        default=os.environ.get("MEMANTO_SKILL_AGENT", DEFAULT_AGENT_ID),
        help="Memanto agent id used for shared skill memory.",
    )
    parser.add_argument(
        "--memanto-command",
        default=os.environ.get("MEMANTO_COMMAND", "memanto"),
        help='Memanto CLI command. Use "python -m memanto" for local checkout runs.',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print memanto commands without executing them.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    pre = subparsers.add_parser("pre", help="Recall memories before a skill starts.")
    pre.add_argument("--skill", required=True, help="Skill name, e.g. tdd.")
    pre.add_argument("--task", required=True, help="Current task or user request.")
    pre.add_argument("--project", default=".", help="Project path.")
    pre.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    pre.set_defaults(func=command_pre)

    post = subparsers.add_parser("post", help="Store memories after a skill ends.")
    post.add_argument("--skill", required=True, help="Skill name, e.g. tdd.")
    post.add_argument("--project", default=".", help="Project path.")
    post.add_argument("--transcript", help="Path to a skill transcript markdown file.")
    post.add_argument("--summary", help="Short handoff summary to store.")
    post.add_argument("--max-memories", type=int, default=8)
    post.set_defaults(func=command_post)

    demo = subparsers.add_parser(
        "demo-distill",
        help="Show extracted memories without calling Memanto.",
    )
    demo.add_argument("transcript", help="Path to a sample transcript.")
    demo.add_argument("--max-memories", type=int, default=8)
    demo.set_defaults(func=command_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

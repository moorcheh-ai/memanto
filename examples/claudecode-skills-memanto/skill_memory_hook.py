"""Memanto hook for command-oriented developer skills.

The hook has two phases:

* ``pre``: recall relevant Memanto context before a skill starts.
* ``post``: extract durable engineering memories from a completed skill summary.

It intentionally depends only on the Python standard library and the installed
``memanto`` CLI so it can sit beside any skills runner without becoming another
framework integration.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable

DEFAULT_AGENT_ENV = "MEMANTO_SKILLS_AGENT"
DEFAULT_AGENT = "developer-skills"

MEMORY_RULES: tuple[tuple[str, str], ...] = (
    ("decision", "decision"),
    ("decisions", "decision"),
    ("convention", "instruction"),
    ("conventions", "instruction"),
    ("preference", "preference"),
    ("preferences", "preference"),
    ("gotcha", "learning"),
    ("gotchas", "learning"),
    ("learned", "learning"),
    ("bugfix", "error"),
    ("bug", "error"),
)


@dataclass(frozen=True)
class MemoryCandidate:
    """A memory extracted from a skill run summary."""

    memory_type: str
    title: str
    content: str


def normalize_spaces(value: str) -> str:
    """Collapse repeated whitespace without changing the semantic text."""

    return re.sub(r"\s+", " ", value).strip()


def split_summary(summary: str) -> Iterable[str]:
    """Split prose into candidate clauses while keeping short summaries usable."""

    if not summary.strip():
        return []

    clauses: list[str] = []
    for part in re.split(r"(?:\r?\n|;|\.\s+)", summary):
        clause = normalize_spaces(part.strip().lstrip("-•* ").strip())
        if clause:
            clauses.append(clause)
    return clauses


def classify_clause(clause: str) -> tuple[str, str] | None:
    """Return ``(memory_type, content)`` for a typed summary clause."""

    match = re.match(r"^(?P<label>[A-Za-z ]{3,24}):\s*(?P<body>.+)$", clause)
    if not match:
        return None

    label = normalize_spaces(match.group("label")).lower()
    body = normalize_spaces(match.group("body"))
    for prefix, memory_type in MEMORY_RULES:
        if label.startswith(prefix):
            return memory_type, body
    return None


def title_for(memory_type: str, content: str) -> str:
    """Create a compact title suitable for Memanto's title limit."""

    prefix = {
        "decision": "Decision",
        "instruction": "Convention",
        "preference": "Preference",
        "learning": "Learning",
        "error": "Bugfix",
    }.get(memory_type, "Memory")
    clean = normalize_spaces(content)
    if len(clean) > 64:
        clean = clean[:61].rstrip() + "..."
    return f"{prefix}: {clean}"


def extract_memories(summary: str) -> list[MemoryCandidate]:
    """Extract typed memories from a completed skill summary."""

    memories: list[MemoryCandidate] = []
    for clause in split_summary(summary):
        classified = classify_clause(clause)
        if not classified:
            continue
        memory_type, content = classified
        memories.append(
            MemoryCandidate(
                memory_type=memory_type,
                title=title_for(memory_type, content),
                content=content,
            )
        )
    return memories


def run_memanto(args: list[str], *, dry_run: bool) -> str:
    """Run a Memanto CLI command or print it in dry-run mode."""

    command = ["memanto", *args]
    if dry_run:
        return "DRY-RUN: " + shlex.join(command)

    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def pre(args: argparse.Namespace) -> int:
    """Recall relevant context before a skill starts."""

    agent = args.agent or os.environ.get(DEFAULT_AGENT_ENV, DEFAULT_AGENT)
    query = normalize_spaces(f"{args.task} {args.files or ''}")
    output = run_memanto(
        ["recall", query, "--agent", agent, "--limit", str(args.limit)],
        dry_run=args.dry_run,
    )
    print("MEMANTO_CONTEXT_START")
    print(output or "No relevant Memanto memories found.")
    print("MEMANTO_CONTEXT_END")
    return 0


def post(args: argparse.Namespace) -> int:
    """Save durable memories after a skill finishes."""

    agent = args.agent or os.environ.get(DEFAULT_AGENT_ENV, DEFAULT_AGENT)
    memories = extract_memories(args.summary)
    if not memories:
        print(
            "No typed memories found. Prefix durable facts with Decision(s):, "
            "Convention(s):, Preference(s):, Gotcha(s):, Learned:, Bugfix:, or Bug:."
        )
        return 0

    for memory in memories:
        output = run_memanto(
            [
                "remember",
                memory.content,
                "--agent",
                agent,
                "--type",
                memory.memory_type,
                "--title",
                memory.title,
                "--tag",
                "developer-skills",
                "--tag",
                args.skill,
            ],
            dry_run=args.dry_run,
        )
        print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command line interface."""

    parser = argparse.ArgumentParser(description="Persist developer-skill context with Memanto.")
    parser.add_argument("--agent", help=f"Memanto agent id. Defaults to ${DEFAULT_AGENT_ENV} or {DEFAULT_AGENT}.")
    subparsers = parser.add_subparsers(required=True)

    pre_parser = subparsers.add_parser("pre", help="Recall context before a skill starts.")
    pre_parser.add_argument("--dry-run", action="store_true", help="Show Memanto CLI calls without executing them.")
    pre_parser.add_argument("--task", required=True, help="Skill command or task description.")
    pre_parser.add_argument("--files", help="Comma-separated files or paths involved in the task.")
    pre_parser.add_argument("--limit", type=int, default=5, help="Maximum memories to recall.")
    pre_parser.set_defaults(func=pre)

    post_parser = subparsers.add_parser("post", help="Save memories after a skill completes.")
    post_parser.add_argument("--dry-run", action="store_true", help="Show Memanto CLI calls without executing them.")
    post_parser.add_argument("--skill", required=True, help="Skill command that produced the summary.")
    post_parser.add_argument("--summary", required=True, help="Concise completed-run summary.")
    post_parser.set_defaults(func=post)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"memanto hook failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

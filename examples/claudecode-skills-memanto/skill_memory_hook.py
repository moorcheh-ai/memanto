"""Memanto hook for command-oriented developer skills.

The hook has three phases:

* ``pre``: recall relevant Memanto context before a skill starts.
* ``event``: capture a mid-session decision or gotcha while a skill runs.
* ``post``: extract durable engineering memories from a completed skill summary.

It intentionally depends only on the Python standard library and the installed
``memanto`` CLI so it can sit beside any skills runner without becoming another
framework integration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_AGENT_ENV = "MEMANTO_SKILLS_AGENT"
DEFAULT_AGENT = "developer-skills"
DEFAULT_TAG = "developer-skills"
DEFAULT_LOCAL_STORE = ".memanto-skills-memory.jsonl"

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


def remember_local(
    store: Path,
    *,
    content: str,
    agent: str,
    memory_type: str,
    title: str,
    tags: list[str],
) -> str:
    """Append one deterministic JSONL record for credential-free demos."""

    store.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "agent": agent,
        "type": memory_type,
        "title": title,
        "content": content,
        "tags": tags,
    }
    with store.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return f"LOCAL-SAVED: {title}"


def recall_local(
    store: Path,
    *,
    query: str,
    agent: str,
    limit: int,
) -> list[dict[str, object]]:
    """Return local records ranked by query-token overlap and recency."""

    if not store.exists():
        return []

    query_tokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
    ranked: list[tuple[int, int, dict[str, object]]] = []
    with store.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("agent") != agent:
                continue
            tags = record.get("tags", [])
            tag_text = (
                " ".join(str(tag) for tag in tags)
                if isinstance(tags, list)
                else str(tags)
            )
            searchable = " ".join(
                [
                    str(record.get("title", "")),
                    str(record.get("content", "")),
                    tag_text,
                ]
            )
            record_tokens = set(re.findall(r"[a-z0-9_]+", searchable.lower()))
            score = len(query_tokens & record_tokens)
            ranked.append((score, index, record))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [record for _, _, record in ranked[:limit]]


def local_context(records: list[dict[str, object]]) -> str:
    """Format local records like a compact injected context block."""

    return "\n".join(
        f"- [{record['type']}] {record['content']}" for record in records
    )


def pre(args: argparse.Namespace) -> int:
    """Recall relevant context before a skill starts."""

    agent = args.agent or os.environ.get(DEFAULT_AGENT_ENV, DEFAULT_AGENT)
    query = normalize_spaces(f"{args.task} {args.files or ''}")
    if args.backend == "local":
        output = local_context(
            recall_local(Path(args.store), query=query, agent=agent, limit=args.limit)
        )
    else:
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
        if args.backend == "local":
            output = remember_local(
                Path(args.store),
                content=memory.content,
                agent=agent,
                memory_type=memory.memory_type,
                title=memory.title,
                tags=[DEFAULT_TAG, args.skill],
            )
        else:
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
                    DEFAULT_TAG,
                    "--tag",
                    args.skill,
                ],
                dry_run=args.dry_run,
            )
        print(output)
    return 0


def event(args: argparse.Namespace) -> int:
    """Save one mid-session memory while a skill is still running."""

    agent = args.agent or os.environ.get(DEFAULT_AGENT_ENV, DEFAULT_AGENT)
    content = normalize_spaces(args.note)
    if args.backend == "local":
        output = remember_local(
            Path(args.store),
            content=content,
            agent=agent,
            memory_type=args.type,
            title=title_for(args.type, content),
            tags=[DEFAULT_TAG, args.skill, "mid-session"],
        )
    else:
        output = run_memanto(
            [
                "remember",
                content,
                "--agent",
                agent,
                "--type",
                args.type,
                "--title",
                title_for(args.type, content),
                "--tag",
                DEFAULT_TAG,
                "--tag",
                args.skill,
                "--tag",
                "mid-session",
            ],
            dry_run=args.dry_run,
        )
    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command line interface."""

    parser = argparse.ArgumentParser(
        description="Persist developer-skill context with Memanto."
    )
    parser.add_argument(
        "--agent",
        help=(
            f"Memanto agent id. Defaults to ${DEFAULT_AGENT_ENV} "
            f"or {DEFAULT_AGENT}."
        ),
    )
    subparsers = parser.add_subparsers(required=True)

    def add_backend_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--backend",
            choices=["memanto", "local"],
            default="memanto",
            help="Use Memanto, or a local JSONL store for credential-free evaluation.",
        )
        subparser.add_argument(
            "--store",
            default=DEFAULT_LOCAL_STORE,
            help="JSONL path used by the local evaluation backend.",
        )

    pre_parser = subparsers.add_parser(
        "pre", help="Recall context before a skill starts."
    )
    add_backend_arguments(pre_parser)
    pre_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show Memanto CLI calls without executing them.",
    )
    pre_parser.add_argument(
        "--task", required=True, help="Skill command or task description."
    )
    pre_parser.add_argument(
        "--files", help="Comma-separated files or paths involved in the task."
    )
    pre_parser.add_argument(
        "--limit", type=int, default=5, help="Maximum memories to recall."
    )
    pre_parser.set_defaults(func=pre)

    post_parser = subparsers.add_parser(
        "post", help="Save memories after a skill completes."
    )
    add_backend_arguments(post_parser)
    post_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show Memanto CLI calls without executing them.",
    )
    post_parser.add_argument(
        "--skill", required=True, help="Skill command that produced the summary."
    )
    post_parser.add_argument(
        "--summary", required=True, help="Concise completed-run summary."
    )
    post_parser.set_defaults(func=post)

    event_parser = subparsers.add_parser(
        "event", help="Save one mid-session memory during a skill run."
    )
    add_backend_arguments(event_parser)
    event_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show Memanto CLI calls without executing them.",
    )
    event_parser.add_argument(
        "--skill", required=True, help="Skill command currently running."
    )
    event_parser.add_argument(
        "--type",
        required=True,
        choices=["decision", "instruction", "preference", "learning", "error"],
        help="Semantic memory type for this event.",
    )
    event_parser.add_argument(
        "--note",
        required=True,
        help="Decision, constraint, gotcha, or bugfix to save now.",
    )
    event_parser.set_defaults(func=event)

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

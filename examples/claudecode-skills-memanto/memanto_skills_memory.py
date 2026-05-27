#!/usr/bin/env python3
"""Claude Code skills memory bridge powered by Memanto.

The default backend is a credential-free JSONL store so reviewers can run the
demo and tests without a Moorcheh API key. Set MEMANTO_SKILLS_BACKEND=cli to
delegate remember/recall calls to the installed ``memanto`` CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

DEFAULT_STORE = ".memanto-skills-memory.jsonl"
SOURCE = "claudecode_skills_memanto"
VALID_MEMORY_TYPES = {
    "context",
    "decision",
    "error",
    "fact",
    "instruction",
    "learning",
    "preference",
}
TYPE_ALIASES = {
    "bug": "error",
    "constraint": "instruction",
    "convention": "preference",
    "lesson": "learning",
    "rule": "instruction",
}


@dataclass(frozen=True)
class MemoryRecord:
    """Structured memory item shared across skill runs."""

    content: str
    memory_type: str
    tags: list[str]
    confidence: float
    provenance: str
    source: str
    skill: str
    created_at: str

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> MemoryRecord:
        """Build a record from a persisted JSON object."""
        return cls(
            content=str(payload.get("content", "")).strip(),
            memory_type=str(payload.get("memory_type", "context")),
            tags=[str(tag) for tag in payload.get("tags", [])],
            confidence=float(payload.get("confidence", 0.8)),
            provenance=str(payload.get("provenance", "observed")),
            source=str(payload.get("source", SOURCE)),
            skill=str(payload.get("skill", "unknown")),
            created_at=str(payload.get("created_at", "")),
        )


class MemoryStore(Protocol):
    """Storage backend capable of remembering and recalling skill context."""

    def remember(self, record: MemoryRecord) -> bool:
        """Persist a memory record. Returns True when a new record was stored."""

    def recall(self, query: str, limit: int) -> list[MemoryRecord]:
        """Return records relevant to the query."""


class LocalJsonlStore:
    """Simple JSONL-backed store used for offline demos and tests."""

    def __init__(self, path: Path) -> None:
        """Create a local store at the given JSONL path."""
        self.path = path

    def _load(self) -> list[MemoryRecord]:
        """Read valid records from disk, skipping malformed rows."""
        if not self.path.exists():
            return []

        records: list[MemoryRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(MemoryRecord.from_json(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return records

    def remember(self, record: MemoryRecord) -> bool:
        """Append a record unless the same content already exists."""
        existing = {item.content.casefold() for item in self._load()}
        if record.content.casefold() in existing:
            return False

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=True) + "\n")
        return True

    def recall(self, query: str, limit: int) -> list[MemoryRecord]:
        """Rank stored records by token overlap with the incoming query."""
        query_terms = _tokenize(query)
        records = self._load()
        scored: list[tuple[int, MemoryRecord]] = []

        for record in records:
            haystack = " ".join(
                [record.content, record.memory_type, record.skill, " ".join(record.tags)]
            )
            terms = _tokenize(haystack)
            overlap = len(query_terms & terms)
            tag_bonus = len(query_terms & set(record.tags))
            score = overlap * 2 + tag_bonus
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        recalled = [record for _, record in scored[:limit]]
        seen = {record.content.casefold() for record in recalled}
        if len(recalled) < limit:
            for record in sorted(records, key=lambda item: item.created_at, reverse=True):
                if record.content.casefold() in seen:
                    continue
                recalled.append(record)
                seen.add(record.content.casefold())
                if len(recalled) >= limit:
                    break
        return recalled


class MemantoCliStore:
    """Adapter that delegates memory operations to the external Memanto CLI."""

    def remember(self, record: MemoryRecord) -> bool:
        """Persist a record through `memanto remember`."""
        command = [
            "memanto",
            "remember",
            record.content,
            "--type",
            record.memory_type,
            "--tags",
            ",".join(record.tags),
            "--confidence",
            str(record.confidence),
            "--provenance",
            record.provenance,
            "--source",
            record.source,
        ]
        subprocess.run(command, check=True)
        return True

    def recall(self, query: str, limit: int) -> list[MemoryRecord]:
        """Fetch relevant context through `memanto recall`."""
        command = ["memanto", "recall", query, "--limit", str(limit)]
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        content = result.stdout.strip()
        if not content:
            return []

        records = [
            MemoryRecord(
                content=line,
                memory_type="context",
                tags=["memanto-cli", "recall"],
                confidence=0.8,
                provenance="imported",
                source=SOURCE,
                skill="memanto-cli",
                created_at=_now(),
            )
            for line in parse_memanto_cli_output(content)[:limit]
        ]
        if records:
            return records

        return [
            MemoryRecord(
                content=re.sub(r"\s+", " ", content),
                memory_type="context",
                tags=["memanto-cli", "recall"],
                confidence=0.8,
                provenance="imported",
                source=SOURCE,
                skill="memanto-cli",
                created_at=_now(),
            )
        ]


def build_store(args: argparse.Namespace) -> MemoryStore:
    """Select the configured memory backend."""
    backend = args.backend or os.getenv("MEMANTO_SKILLS_BACKEND", "local")
    if backend == "cli":
        return MemantoCliStore()
    return LocalJsonlStore(Path(args.store or os.getenv("MEMANTO_SKILLS_STORE", DEFAULT_STORE)))


def extract_memories(transcript: str, skill: str, tags: list[str]) -> list[MemoryRecord]:
    """Extract explicit memory lines from a skill transcript."""
    records: list[MemoryRecord] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue

        match = re.match(
            r"^(decision|preference|instruction|fact|learning|error|context):\s*(.+)$",
            line,
            re.I,
        )
        if not match:
            continue

        memory_type = normalize_memory_type(match.group(1))
        content = match.group(2).strip()
        if not content:
            continue

        record_tags = sorted({*tags, skill, memory_type})
        records.append(
            MemoryRecord(
                content=content,
                memory_type=memory_type,
                tags=record_tags,
                confidence=0.9 if memory_type in {"decision", "instruction"} else 0.82,
                provenance="observed",
                source=SOURCE,
                skill=skill,
                created_at=_now(),
            )
        )
    return records


def render_context(records: list[MemoryRecord]) -> str:
    """Format recalled records as a compact prompt context block."""
    if not records:
        return "<!-- memanto-skills-context: none -->"

    lines = ["<!-- memanto-skills-context -->", "## Relevant Memanto Skill Memory"]
    for record in records:
        tag_text = ",".join(record.tags[:5])
        lines.append(
            f"- [{record.memory_type}] {record.content} "
            f"(skill={record.skill}; confidence={record.confidence:.2f}; tags={tag_text})"
        )
    lines.append("<!-- /memanto-skills-context -->")
    return "\n".join(lines)


def command_pre(args: argparse.Namespace) -> int:
    """Handle the pre-run recall command."""
    prompt = read_prompt(args.prompt, args.prompt_file)
    query = f"{args.skill} {prompt}".strip()
    records = build_store(args).recall(query, args.limit)
    print(render_context(records))
    return 0


def command_post(args: argparse.Namespace) -> int:
    """Handle post-run transcript extraction."""
    transcript = read_text_arg(args.transcript, args.transcript_file)
    tags = parse_tags(args.tags)
    records = extract_memories(transcript, args.skill, tags)
    store = build_store(args)

    stored = 0
    for record in records:
        if store.remember(record):
            stored += 1

    print(f"extracted={len(records)} stored={stored}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    """Run a child command with recalled skill context injected."""
    command = list(args.child_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("run requires a child command after --", file=sys.stderr)
        return 2

    prompt = read_prompt(args.prompt, args.prompt_file)
    store = build_store(args)
    records = store.recall(f"{args.skill} {prompt}".strip(), args.limit)
    context = render_context(records)

    env = os.environ.copy()
    env["MEMANTO_SKILL_CONTEXT"] = context
    env["MEMANTO_SKILL_NAME"] = args.skill
    env["MEMANTO_SKILL_PROMPT"] = prompt

    print(context)
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    transcript = "\n".join(
        [
            f"Skill: {args.skill}",
            f"Prompt: {prompt}",
            "Injected context:",
            context,
            "Child stdout:",
            result.stdout,
            "Child stderr:",
            result.stderr,
        ]
    )
    stored = 0
    for record in extract_memories(transcript, args.skill, parse_tags(args.tags)):
        if store.remember(record):
            stored += 1

    print(f"run exit={result.returncode} stored={stored}")
    return result.returncode


def command_validate(args: argparse.Namespace) -> int:
    """Run an offline proof that memories survive across skill names."""
    if args.store:
        store_path = Path(args.store)
    else:
        fd, tmp_path = tempfile.mkstemp(prefix="memanto-skills-", suffix=".jsonl")
        os.close(fd)
        store_path = Path(tmp_path)
    if args.reset and store_path.exists():
        store_path.unlink()

    store = LocalJsonlStore(store_path)
    session_a = "\n".join(
        [
            "Decision: Use FastAPI routers for HTTP boundaries.",
            "Preference: Write pytest coverage before changing shared behavior.",
            "Instruction: Keep service functions pure unless persistence is required.",
        ]
    )
    for record in extract_memories(session_a, "grill-with-docs", ["demo", "payments"]):
        store.remember(record)

    records = store.recall("tdd invoice endpoint FastAPI pytest service", limit=5)
    rendered = render_context(records)
    checks = [
        "FastAPI routers" in rendered,
        "pytest coverage" in rendered,
        "service functions pure" in rendered,
    ]
    if not all(checks):
        print(rendered)
        print("validation failed", file=sys.stderr)
        return 1

    print(rendered)
    print(f"validation passed store={store_path}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    """Print a readable two-session memory handoff demo."""
    store_path = Path(args.store or "demo/memanto-skills-demo.jsonl")
    if args.reset and store_path.exists():
        store_path.unlink()

    post_args = argparse.Namespace(
        backend="local",
        store=str(store_path),
        skill="grill-with-docs",
        transcript="\n".join(
            [
                "Decision: Use FastAPI routers for HTTP boundaries.",
                "Preference: Write pytest coverage before changing shared behavior.",
                "Instruction: Keep service functions pure unless persistence is required.",
            ]
        ),
        transcript_file=None,
        tags="demo,payments,architecture",
    )
    pre_args = argparse.Namespace(
        backend="local",
        store=str(store_path),
        skill="tdd",
        prompt="Implement the invoice endpoint after the architecture review.",
        prompt_file=None,
        limit=5,
    )

    print("Session A: /grill-with-docs stores architecture decisions")
    command_post(post_args)
    print("\nSession B: /tdd starts in a fresh shell and receives relevant context")
    command_pre(pre_args)
    print(f"\nDemo memory store: {store_path}")
    return 0


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    """Read a prompt from an argument value or a file."""
    if prompt_file:
        return read_file_or_stdin(prompt_file)
    return prompt or ""


def read_text_arg(text: str | None, file_name: str | None) -> str:
    """Read arbitrary text from an argument value or a file."""
    if file_name:
        return read_file_or_stdin(file_name)
    return text or ""


def read_file_or_stdin(file_name: str) -> str:
    """Read UTF-8 text from a path, or stdin when the path is '-'."""
    if file_name == "-":
        return sys.stdin.read()
    return Path(file_name).read_text(encoding="utf-8")


def normalize_memory_type(memory_type: str) -> str:
    """Normalize a memory type to the accepted vocabulary."""
    normalized = memory_type.strip().casefold().replace(" ", "-")
    normalized = TYPE_ALIASES.get(normalized, normalized)
    if normalized not in VALID_MEMORY_TYPES:
        return "context"
    return normalized


def parse_tags(tags: str | None) -> list[str]:
    """Parse a comma-separated tag string into stable tag slugs."""
    if not tags:
        return []
    parsed: list[str] = []
    for tag in tags.split(","):
        sanitized_tag = re.sub(r"[^a-z0-9-]+", "-", tag.strip().casefold()).strip("-")
        if sanitized_tag:
            parsed.append(sanitized_tag)
    return parsed


def parse_memanto_cli_output(content: str) -> list[str]:
    """Convert human-rendered Memanto CLI output into memory text lines."""
    memories: list[str] = []
    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip(" \t-*•|│┃")).strip()
        if not line:
            continue
        if line.casefold() in {"memories", "memory", "results", "no memories found"}:
            continue
        memories.append(line)
    return memories


def _tokenize(text: str) -> set[str]:
    """Split text into lower-cased search tokens."""
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", text.casefold())
        if token not in {"the", "and", "with", "from", "this", "that"}
    }


def _now() -> str:
    """Return the current UTC timestamp for persisted records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description="Memanto bridge for Claude Code skills")
    parser.add_argument("--backend", choices=["local", "cli"], default=None)
    parser.add_argument("--store", default=None, help="Path for the local JSONL backend")

    subparsers = parser.add_subparsers(dest="command", required=True)

    pre = subparsers.add_parser("pre", help="Recall and render context before a skill run")
    pre.add_argument("--skill", required=True)
    pre.add_argument("--prompt", default=None)
    pre.add_argument("--prompt-file", default=None)
    pre.add_argument("--limit", type=int, default=5)
    pre.set_defaults(func=command_pre)

    post = subparsers.add_parser("post", help="Extract and store memories after a skill run")
    post.add_argument("--skill", required=True)
    post.add_argument("--transcript", default=None)
    post.add_argument("--transcript-file", default=None)
    post.add_argument("--tags", default=None)
    post.set_defaults(func=command_post)

    run = subparsers.add_parser("run", help="Run a skill command with memory context")
    run.add_argument("--skill", required=True)
    run.add_argument("--prompt", default=None)
    run.add_argument("--prompt-file", default=None)
    run.add_argument("--tags", default=None)
    run.add_argument("--limit", type=int, default=5)
    run.add_argument("child_command", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    validate = subparsers.add_parser("validate", help="Run the offline cross-session proof")
    validate.add_argument("--reset", action="store_true")
    validate.set_defaults(func=command_validate)

    demo = subparsers.add_parser("run-demo", help="Run the readable two-session demo")
    demo.add_argument("--reset", action="store_true")
    demo.set_defaults(func=command_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected command."""
    args = make_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

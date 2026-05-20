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


class MemantoSdkBackend:
    """Backend that uses Memanto's Python SDK client directly."""

    def __init__(self, agent_id: str | None = None) -> None:
        from memanto.cli.commands._shared import get_client

        self.client = get_client()
        self.agent_id = agent_id or self.client.agent_id
        if not self.agent_id:
            raise ValueError(
                "No active Memanto agent. Run `memanto agent create` or pass "
                "MEMANTO_AGENT_ID."
            )

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=["decision"],
        )
        return _extract_sdk_memory_lines(result)

    def remember(
        self,
        content: str,
        memory_type: str,
        title: str,
        tags: list[str],
        confidence: float,
    ) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source="claudecode-skills-memanto",
            provenance="inferred",
        )


class LocalJsonlBackend:
    """Credential-free backend for demos and reviewer validation."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        if not self.path.exists():
            return []
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        scored: list[tuple[int, str]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            content = str(record.get("content", ""))
            haystack = " ".join(
                [content, str(record.get("title", "")), " ".join(record.get("tags", []))]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, content))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [content for _, content in scored[:limit]]

    def remember(
        self,
        content: str,
        memory_type: str,
        title: str,
        tags: list[str],
        confidence: float,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "content": content,
            "memory_type": memory_type,
            "title": title,
            "tags": tags,
            "confidence": confidence,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


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


def _extract_sdk_memory_lines(result: dict[str, object]) -> list[str]:
    memories = result.get("memories", [])
    if not isinstance(memories, list):
        return []

    lines: list[str] = []
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        content = memory.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
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
        command_parser.add_argument(
            "--backend",
            choices=("memanto-sdk", "memanto-cli", "local-jsonl"),
            default=os.environ.get("MEMANTO_SKILLS_BACKEND", "memanto-cli"),
        )
        command_parser.add_argument(
            "--store",
            default=os.environ.get(
                "MEMANTO_SKILLS_STORE",
                str(Path(".memanto-skills-preview.jsonl")),
            ),
            help="JSONL path used by --backend local-jsonl.",
        )

    args = parser.parse_args(argv)
    if args.backend == "local-jsonl":
        backend: MemoryBackend = LocalJsonlBackend(Path(args.store))
    elif args.backend == "memanto-sdk":
        backend = MemantoSdkBackend(os.environ.get("MEMANTO_AGENT_ID"))
    else:
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

#!/usr/bin/env python3
"""Cross-skill memory bridge for Memanto + mattpocock/skills.

Wraps skill executions with Memanto memory recall (before) and
engineering-memory distillation (after) so architectural decisions
persist across separate terminal sessions.

Three backends are supported:
- ``local``: credential-free JSONL file for reviewer validation.
- ``sdk``: direct Python SDK client (no subprocess overhead).
- ``cli``: shell out to the ``memanto`` CLI (fallback).

Usage::

    # Before a skill runs
    python skill_memory_hook.py recall --skill tdd --task "Add retry logic" --file src/retries.py

    # After a skill completes
    python skill_memory_hook.py store --skill tdd --task "Add retry logic" --file src/retries.py --transcript-file /tmp/out.txt

    # Full lifecycle wrapper
    python skill_memory_hook.py wrap --skill tdd --task "Add retry logic" --file src/retries.py -- python -m pytest tests/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 5
DEFAULT_AGENT = "claude-code-skills"
DEFAULT_CONFIDENCE = 0.78
MAX_CONTENT_LENGTH = 1200

ENV_CONTEXT = "MEMANTO_SKILL_CONTEXT"
ENV_BACKEND = "MEMANTO_SKILLS_BACKEND"
ENV_AGENT = "MEMANTO_SKILLS_AGENT"

MARKER_OPEN = "<memanto-engineering-memory>"
MARKER_CLOSE = "</memanto-engineering-memory>"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillRun:
    """Immutable context for a single skill invocation."""

    skill: str
    task: str
    files: tuple[str, ...] = ()
    transcript: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def query(self) -> str:
        parts = [self.skill, self.task]
        parts.extend(self.files)
        return " ".join(parts)


@dataclass
class DistilledMemory:
    """A single piece of durable engineering context."""

    content: str
    memory_type: str  # decision | preference | instruction | context
    tags: list[str] = field(default_factory=list)
    confidence: float = DEFAULT_CONFIDENCE


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class MemoryBackend(Protocol):
    """Pluggable storage so tests and previews avoid network calls."""

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]: ...

    def store(self, memory: DistilledMemory) -> None: ...


# ---------------------------------------------------------------------------
# Local JSONL backend (credential-free)
# ---------------------------------------------------------------------------


class LocalBackend:
    """File-based JSONL backend for demos and reviewer validation."""

    def __init__(self, path: Path) -> None:
        self.path = path

    # -- public --

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        if not self.path.exists():
            return []
        terms = _tokenise(query)
        scored: list[tuple[int, str]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            haystack = " ".join(
                [
                    record.get("content", ""),
                    record.get("title", ""),
                    " ".join(record.get("tags", [])),
                ]
            ).lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                scored.append((score, record["content"]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def store(self, memory: DistilledMemory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "content": memory.content,
            "memory_type": memory.memory_type,
            "tags": memory.tags,
            "confidence": memory.confidence,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# SDK backend (direct Python client)
# ---------------------------------------------------------------------------


class SdkBackend:
    """Direct SDK client — no subprocess overhead, full type safety."""

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("MOORCHEH_API_KEY is required for SDK mode")
        self._api_key = api_key.strip()
        self._agent_id = agent_id
        self._client: object | None = None

    # -- lazy init --

    def _get_client(self):
        if self._client is None:
            from memanto.cli.client.sdk_client import SdkClient

            client = SdkClient(self._api_key)
            client.create_agent(self._agent_id, pattern="tool")
            client.activate_agent(self._agent_id)
            self._client = client
        return self._client

    # -- public --

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        client = self._get_client()
        result = client.recall(
            agent_id=self._agent_id,
            query=query,
            limit=limit,
            type=["decision", "preference", "instruction"],
        )
        memories: list[str] = []
        for m in result.get("memories", []):
            content = m.get("content", "")
            if content:
                memories.append(content)
        return memories

    def store(self, memory: DistilledMemory) -> None:
        client = self._get_client()
        client.remember(
            agent_id=self._agent_id,
            memory_type=memory.memory_type,
            title=_truncate(memory.content, 80),
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source="claudecode-skills-memanto",
            provenance="inferred",
        )


# ---------------------------------------------------------------------------
# CLI backend (subprocess fallback)
# ---------------------------------------------------------------------------


class CliBackend:
    """Shells out to the ``memanto`` CLI."""

    def __init__(
        self, agent_id: str = DEFAULT_AGENT, executable: str = "memanto"
    ) -> None:
        self._agent_id = agent_id
        self._executable = executable

    def recall(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        result = subprocess.run(
            [
                self._executable,
                "recall",
                query,
                "--limit",
                str(limit),
                "--type",
                "decision",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        return _extract_cli_output(result.stdout)

    def store(self, memory: DistilledMemory) -> None:
        args = [
            self._executable,
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--title",
            _truncate(memory.content, 80),
            "--source",
            "claudecode-skills-memanto",
            "--provenance",
            "inferred",
            "--confidence",
            f"{memory.confidence:.2f}",
        ]
        if memory.tags:
            args.extend(["--tags", ",".join(memory.tags)])
        subprocess.run(args, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Memory distillation
# ---------------------------------------------------------------------------


class MemoryDistiller:
    """Extract durable engineering signals from a skill transcript.

    Uses pattern matching with confidence scoring rather than naive
    regex — each matched pattern contributes a weighted confidence
    value so stronger signals rank higher.
    """

    # (compiled pattern, memory_type, base_confidence)
    _RULES: list[tuple[re.Pattern[str], str, float]] = [
        (
            re.compile(r"\b(decision|decided|we will|we should)\b[:\s]", re.I),
            "decision",
            0.85,
        ),
        (
            re.compile(r"\b(prefer|preference|convention|style guide)\b[:\s]", re.I),
            "preference",
            0.75,
        ),
        (
            re.compile(
                r"\b(must|must not|never|always|required|prohibited)\b[:\s]", re.I
            ),
            "instruction",
            0.90,
        ),
        (
            re.compile(r"\b(quirk|gotcha|caveat|note that|beware)\b[:\s]", re.I),
            "context",
            0.65,
        ),
        (
            re.compile(r"\b(trade.?off|compromise|sacrifice)\b[:\s]", re.I),
            "context",
            0.70,
        ),
        (re.compile(r"\b(follow.?up|todo|next step)\b[:\s]", re.I), "context", 0.60),
    ]

    def distill(self, transcript: str, run: SkillRun) -> list[DistilledMemory]:
        if not transcript:
            return []

        seen: set[str] = set()
        memories: list[DistilledMemory] = []
        tags = _build_tags(run)

        for line in transcript.splitlines():
            line = line.strip(" -\t*")
            if len(line) < 20:
                continue

            for pattern, mem_type, base_conf in self._RULES:
                match = pattern.search(line)
                if not match:
                    continue

                cleaned = pattern.sub("", line, count=1).strip(" :-")
                cleaned = re.sub(r"\s+", " ", cleaned)
                if len(cleaned) < 15:
                    continue

                dedup_key = cleaned.lower()
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                memories.append(
                    DistilledMemory(
                        content=_truncate(cleaned, MAX_CONTENT_LENGTH),
                        memory_type=mem_type,
                        tags=tags,
                        confidence=base_conf,
                    )
                )
                break  # one match per line

        return memories[:12]


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------


def build_context_block(memories: list[str]) -> str:
    """Format recalled memories into an injectable prompt block."""
    if not memories:
        return ""
    bullets = "\n".join(f"- {m}" for m in memories)
    return f"{MARKER_OPEN}\nRelevant prior engineering decisions:\n{bullets}\n{MARKER_CLOSE}"


def set_env_context(block: str) -> None:
    """Export the context block to MEMANTO_SKILL_CONTEXT for child processes."""
    if block:
        os.environ[ENV_CONTEXT] = block


def get_env_context() -> str:
    """Read any previously set context from the environment."""
    return os.environ.get(ENV_CONTEXT, "")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_recall(args: argparse.Namespace) -> int:
    run = _build_run(args)
    backend = _make_backend(args)
    memories = backend.recall(run.query, limit=DEFAULT_LIMIT)
    block = build_context_block(memories)
    if block:
        print(block)
        set_env_context(block)
    return 0


def cmd_store(args: argparse.Namespace) -> int:
    run = _build_run(args, read_transcript=True)
    backend = _make_backend(args)
    distiller = MemoryDistiller()
    memories = distiller.distill(run.transcript, run)
    for m in memories:
        backend.store(m)
    print(f"stored_memories={len(memories)}")
    return 0


def cmd_wrap(args: argparse.Namespace) -> int:
    cmd = getattr(args, "skill_command", None) or []
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("wrap requires a command after --", file=sys.stderr)
        return 2

    # Phase 1: recall
    recall_args = argparse.Namespace(**vars(args))
    recall_args.transcript = None
    recall_args.transcript_file = None
    cmd_recall(recall_args)

    # Phase 2: run command
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    transcript = "\n".join(p for p in (result.stdout, result.stderr) if p.strip())
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)

    # Phase 3: store
    store_args = argparse.Namespace(**vars(args))
    store_args.transcript = transcript
    store_args.transcript_file = None
    cmd_store(store_args)

    return result.returncode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_run(args: argparse.Namespace, *, read_transcript: bool = False) -> SkillRun:
    transcript = ""
    if read_transcript:
        transcript = args.transcript or ""
        if not transcript and args.transcript_file:
            transcript = Path(args.transcript_file).read_text(encoding="utf-8")
        if not transcript and not sys.stdin.isatty():
            transcript = sys.stdin.read()
    metadata = {}
    if getattr(args, "metadata", None):
        metadata = json.loads(args.metadata)
    return SkillRun(
        skill=args.skill,
        task=args.task,
        files=tuple(args.file or ()),
        transcript=transcript,
        metadata=metadata,
    )


def _make_backend(args: argparse.Namespace) -> MemoryBackend:
    backend_name = args.backend or os.environ.get(ENV_BACKEND, "local")
    agent_id = getattr(args, "agent", None) or os.environ.get(ENV_AGENT, DEFAULT_AGENT)

    if backend_name == "sdk":
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        return SdkBackend(api_key, agent_id)
    if backend_name == "cli":
        return CliBackend(agent_id)
    store = getattr(args, "store", None) or os.environ.get(
        "MEMANTO_SKILLS_STORE",
        str(Path(".memanto-skills-preview.jsonl")),
    )
    return LocalBackend(Path(store))


def _build_tags(run: SkillRun) -> list[str]:
    tags = ["claude-code-skills", f"skill:{run.skill}"]
    for f in run.files[:5]:
        tags.append(f"file:{Path(f).name}")
    return tags


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_./-]{3,}", text.lower()))


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_cli_output(output: str) -> list[str]:
    lines: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith(("Found ", "ID:", "Type:", "Completed ")):
            continue
        if "Memory " in line and "Score:" in line:
            continue
        lines.append(line)
    return lines[:DEFAULT_LIMIT]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("recall", "Inject recalled memory before a skill"),
        ("store", "Distill and store memory after a skill"),
        ("wrap", "Run a command with full memory lifecycle"),
    ]:
        sub = subs.add_parser(name, help=help_text)
        sub.add_argument("--skill", required=True)
        sub.add_argument("--task", required=True)
        sub.add_argument("--file", action="append", default=[])
        sub.add_argument("--metadata")
        sub.add_argument("--transcript")
        sub.add_argument("--transcript-file")
        sub.add_argument("--agent", default=DEFAULT_AGENT)
        sub.add_argument(
            "--backend",
            choices=("local", "sdk", "cli"),
            default=os.environ.get(ENV_BACKEND, "local"),
        )
        sub.add_argument("--store", default=str(Path(".memanto-skills-preview.jsonl")))
        if name == "wrap":
            sub.add_argument("skill_command", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return {"recall": cmd_recall, "store": cmd_store, "wrap": cmd_wrap}[args.command](
        args
    )


if __name__ == "__main__":
    raise SystemExit(main())

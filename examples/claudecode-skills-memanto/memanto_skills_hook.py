#!/usr/bin/env python3
"""Bridge Claude Code-style skill runs through Memanto memory."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


DEFAULT_LIMIT = 5
MEMORY_PATTERNS: tuple[tuple[str, str, float, re.Pattern[str]], ...] = (
    ("decision", "Decision", 0.88, re.compile(r"\b(?:decision|decided):\s*(.+)", re.I)),
    ("preference", "Preference", 0.82, re.compile(r"\b(?:preference|prefer):\s*(.+)", re.I)),
    ("instruction", "Constraint", 0.9, re.compile(r"\b(?:must|never|always):\s*(.+)", re.I)),
    ("context", "Quirk", 0.76, re.compile(r"\b(?:quirk|caveat|gotcha):\s*(.+)", re.I)),
    ("context", "Trade-off", 0.74, re.compile(r"\b(?:trade-?off):\s*(.+)", re.I)),
)


@runtime_checkable
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


class TranscriptDistiller(Protocol):
    """Optional backend capability for LLM-backed memory extraction."""

    def distill_transcript(self, run: "SkillRun") -> list[dict[str, object]]:
        """Return durable memories inferred from a completed skill transcript."""


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

    def distill_transcript(self, run: SkillRun) -> list[dict[str, object]]:
        """Use Memanto's backend LLM to extract durable engineering memories."""
        transcript = _compact(run.transcript, max_chars=6000)
        if not transcript:
            return []

        prompt = (
            "Extract durable developer memories from this completed skill run. "
            "Return only JSON with a top-level `memories` array. Each item must have "
            "`type` as one of decision, preference, instruction, context; `title`; "
            "`content`; and `confidence` from 0 to 1. Keep memories reusable across "
            "future terminal sessions and ignore temporary status updates.\n\n"
            f"Skill: {run.skill}\n"
            f"Task: {run.task}\n"
            f"Files: {', '.join(run.files) or 'not specified'}\n"
            f"Transcript:\n{transcript}"
        )

        answer = _call_sdk_answer(self.client, self.agent_id, prompt)
        if not answer:
            return []
        return _parse_distilled_memories(run, answer)


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


def _call_sdk_answer(client: object, agent_id: str, prompt: str) -> str:
    answer_method = getattr(client, "answer", None)
    if not callable(answer_method):
        return ""

    attempts: tuple[dict[str, object], ...] = (
        {"agent_id": agent_id, "question": prompt},
        {"agent_id": agent_id, "query": prompt},
        {"agent_id": agent_id, "prompt": prompt},
    )
    for kwargs in attempts:
        try:
            result = answer_method(**kwargs)
        except TypeError:
            continue
        text = _extract_answer_text(result)
        if text:
            return text
    return ""


def _extract_answer_text(result: object) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("answer", "content", "text", "result"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    for key in ("answer", "content", "text", "result"):
        value = getattr(result, key, None)
        if isinstance(value, str):
            return value
    return ""


def _parse_distilled_memories(run: SkillRun, answer: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(_extract_json_object(answer))
    except json.JSONDecodeError:
        return []

    raw_memories = payload.get("memories", [])
    if not isinstance(raw_memories, list):
        return []

    tags = ["claude-code-skills", f"skill:{run.skill}"]
    tags.extend(f"file:{Path(path).name}" for path in run.files[:5])

    memories: list[dict[str, object]] = []
    for item in raw_memories:
        if not isinstance(item, dict):
            continue
        memory_type = str(item.get("type", "decision")).lower()
        if memory_type not in {"decision", "preference", "instruction", "context"}:
            memory_type = "decision"
        content = _compact(str(item.get("content", "")), max_chars=700)
        if not content:
            continue
        title = _compact(str(item.get("title") or f"{run.skill} memory"), max_chars=80)
        confidence = _coerce_confidence(item.get("confidence"), default=0.84)
        memories.append(
            {
                "content": content,
                "memory_type": memory_type,
                "title": title,
                "tags": tags,
                "confidence": confidence,
            }
        )
    return memories[:DEFAULT_LIMIT]


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def _coerce_confidence(value: object, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, confidence))


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

    memories = _extract_structured_memories(run, transcript, tags)
    if memories:
        return memories

    return [_build_memory(run, transcript, "decision", "Skill outcome", tags, 0.78)]


def _extract_structured_memories(
    run: SkillRun,
    transcript: str,
    tags: list[str],
) -> list[dict[str, object]]:
    memories: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", transcript):
        sentence = sentence.strip(" -\t")
        if not sentence:
            continue
        for memory_type, label, confidence, pattern in MEMORY_PATTERNS:
            match = pattern.search(sentence)
            if not match:
                continue
            detail = _compact(match.group(1).strip(), max_chars=420)
            if not detail:
                continue
            key = (memory_type, detail.lower())
            if key in seen:
                continue
            seen.add(key)
            memories.append(_build_memory(run, detail, memory_type, label, tags, confidence))
            break
    return memories[:DEFAULT_LIMIT]


def _build_memory(
    run: SkillRun,
    detail: str,
    memory_type: str,
    label: str,
    tags: list[str],
    confidence: float,
) -> dict[str, object]:
    files = ", ".join(run.files) or "not specified"
    content = (
        f"Skill `{run.skill}` handled task `{run.task}`. "
        f"Files in scope: {files}. {label}: {detail}"
    )
    return {
        "content": content,
        "memory_type": memory_type,
        "title": f"{run.skill}: {label.lower()} for {run.task[:54]}",
        "tags": tags,
        "confidence": confidence,
    }


def store_completed_run(run: SkillRun, backend: MemoryBackend) -> int:
    """Persist memories inferred from a finished skill run."""
    memories: list[dict[str, object]] = []
    distiller = getattr(backend, "distill_transcript", None)
    if callable(distiller):
        memories = distiller(run)
    if not memories:
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


def build_backend(backend_name: str, store: str | Path | None = None) -> MemoryBackend:
    """Construct the configured backend shared by hooks and wrappers."""
    if backend_name == "local-jsonl":
        return LocalJsonlBackend(
            Path(
                store
                or os.environ.get(
                    "MEMANTO_SKILLS_STORE",
                    str(Path(".memanto-skills-preview.jsonl")),
                )
            )
        )
    if backend_name == "memanto-sdk":
        return MemantoSdkBackend(os.environ.get("MEMANTO_AGENT_ID"))
    if backend_name == "memanto-cli":
        return MemantoCliBackend(os.environ.get("MEMANTO_EXECUTABLE", "memanto"))
    raise ValueError(f"Unsupported backend: {backend_name}")


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
    backend = build_backend(args.backend, args.store)
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

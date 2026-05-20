#!/usr/bin/env python3
"""Memory lifecycle hooks for Claude Code-style developer skills.

The module is intentionally dependency-light so the example can be reviewed in
three modes:

* local preview: JSONL store, no credentials, deterministic distillation
* live Memanto CLI: uses the existing ``memanto remember`` / ``memanto recall``
* wrapper mode: runs any skill command between pre and post lifecycle hooks
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


DEFAULT_LIMIT = 5
DEFAULT_STORE = ".memanto-skills-preview/memories.jsonl"
SOURCE = "claudecode-skills-memanto"


@dataclass(frozen=True)
class SkillRun:
    skill: str
    task: str
    files: tuple[str, ...] = ()
    transcript: str = ""
    cwd: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def query(self) -> str:
        parts = [self.skill, self.task, *self.files, self.cwd]
        return " ".join(part for part in parts if part).strip()


@dataclass(frozen=True)
class EngineeringMemory:
    title: str
    content: str
    memory_type: str = "decision"
    tags: tuple[str, ...] = ()
    confidence: float = 0.82
    source_skill: str = ""
    created_at: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class MemoryBackend(Protocol):
    def recall(self, run: SkillRun, limit: int = DEFAULT_LIMIT) -> list[EngineeringMemory]:
        """Return memories relevant to a skill run."""

    def store(self, memory: EngineeringMemory) -> None:
        """Persist one engineering memory."""


class RuleBasedDistiller:
    """Credential-free distiller used by local preview and tests.

    The live path stores these distilled decisions in Memanto. If a team wants
    fully LLM-generated summaries, this class is the narrow replacement point.
    """

    DECISION_PATTERNS = (
        r"\b(?:decided|decision|choose|chosen|use|prefer|keep|preserve|avoid|must|should)\b[^.!\n]*(?:[.!\n]|$)",
        r"\b(?:implemented|fixed|changed|refactored|validated)\b[^.!\n]*(?:[.!\n]|$)",
    )

    def distill(self, run: SkillRun) -> list[EngineeringMemory]:
        transcript = _compact(run.transcript)
        if not transcript:
            return []

        snippets = self._extract_decision_snippets(transcript)
        content = self._build_content(run, snippets or [transcript])
        return [
            EngineeringMemory(
                title=_title_for(run),
                content=content,
                tags=_tags_for(run),
                confidence=0.86 if snippets else 0.72,
                source_skill=run.skill,
                created_at=_now(),
            )
        ]

    def _extract_decision_snippets(self, transcript: str) -> list[str]:
        snippets: list[str] = []
        for pattern in self.DECISION_PATTERNS:
            for match in re.finditer(pattern, transcript, flags=re.IGNORECASE):
                snippet = _compact(match.group(0), max_chars=280)
                if snippet and snippet not in snippets:
                    snippets.append(snippet)
        return snippets[:4]

    def _build_content(self, run: SkillRun, snippets: list[str]) -> str:
        files = ", ".join(run.files) if run.files else "not specified"
        decisions = " ".join(snippets)
        return (
            f"Skill `{run.skill}` completed task `{run.task}`. "
            f"Files in scope: {files}. "
            f"Durable engineering memory: {decisions}"
        )


class LocalJsonlBackend:
    """Credential-free backend for reviewer preview and tests."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path

    def recall(self, run: SkillRun, limit: int = DEFAULT_LIMIT) -> list[EngineeringMemory]:
        query_terms = _terms(run.query)
        scored: list[tuple[int, EngineeringMemory]] = []
        for memory in self._read_all():
            haystack = " ".join(
                [
                    memory.title,
                    memory.content,
                    " ".join(memory.tags),
                    memory.source_skill,
                ]
            )
            score = _score(query_terms, haystack)
            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def store(self, memory: EngineeringMemory) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.store_path.open("a", encoding="utf-8") as handle:
            handle.write(memory.to_json() + "\n")

    def _read_all(self) -> list[EngineeringMemory]:
        if not self.store_path.exists():
            return []

        memories: list[EngineeringMemory] = []
        for line in self.store_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            memories.append(
                EngineeringMemory(
                    title=str(record.get("title", "")),
                    content=str(record.get("content", "")),
                    memory_type=str(record.get("memory_type", "decision")),
                    tags=tuple(record.get("tags", ())),
                    confidence=float(record.get("confidence", 0.0)),
                    source_skill=str(record.get("source_skill", "")),
                    created_at=str(record.get("created_at", "")),
                )
            )
        return memories


class MemantoCliBackend:
    """Live backend using the installed Memanto CLI and active agent session."""

    def __init__(self, executable: str = "memanto") -> None:
        self.executable = executable

    def recall(self, run: SkillRun, limit: int = DEFAULT_LIMIT) -> list[EngineeringMemory]:
        completed = subprocess.run(
            [
                self.executable,
                "recall",
                run.query,
                "--type",
                "decision",
                "--tags",
                SOURCE,
                "--limit",
                str(limit),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return []
        return _parse_memanto_recall(completed.stdout)

    def store(self, memory: EngineeringMemory) -> None:
        tags = ",".join(memory.tags)
        args = [
            self.executable,
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--title",
            memory.title,
            "--source",
            SOURCE,
            "--provenance",
            "inferred",
            "--confidence",
            f"{memory.confidence:.2f}",
        ]
        if tags:
            args.extend(["--tags", tags])
        subprocess.run(args, check=True)


def build_injection_block(run: SkillRun, backend: MemoryBackend, limit: int) -> str:
    memories = backend.recall(run, limit=limit)
    if not memories:
        return ""

    lines = [
        "<memanto-engineering-memory>",
        "Apply these prior engineering decisions during this skill run:",
    ]
    for memory in memories:
        lines.append(f"- {memory.content}")
    lines.append("</memanto-engineering-memory>")
    return "\n".join(lines)


def store_completed_run(
    run: SkillRun,
    backend: MemoryBackend,
    distiller: RuleBasedDistiller | None = None,
) -> int:
    distiller = distiller or RuleBasedDistiller()
    memories = distiller.distill(run)
    for memory in memories:
        backend.store(memory)
    return len(memories)


def run_wrapped_command(
    run: SkillRun,
    command: list[str],
    backend: MemoryBackend,
    limit: int,
) -> int:
    injection = build_injection_block(run, backend, limit)
    if injection:
        print(injection)
        print()

    env = os.environ.copy()
    if injection:
        env["MEMANTO_SKILL_CONTEXT"] = injection

    completed = subprocess.run(command, capture_output=True, text=True, env=env)
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)

    transcript = "\n".join(
        part for part in (injection, completed.stdout, completed.stderr) if part.strip()
    )
    store_completed_run(
        SkillRun(
            skill=run.skill,
            task=run.task,
            files=run.files,
            transcript=transcript,
            cwd=run.cwd,
            metadata=run.metadata,
        ),
        backend,
    )
    return completed.returncode


def backend_from_args(args: argparse.Namespace) -> MemoryBackend:
    if args.backend == "local":
        return LocalJsonlBackend(Path(args.store))
    return MemantoCliBackend(os.environ.get("MEMANTO_EXECUTABLE", "memanto"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject and store Memanto engineering memory around skill runs."
    )
    parser.add_argument(
        "--backend",
        choices=("local", "memanto"),
        default=os.environ.get("MEMANTO_SKILLS_BACKEND", "local"),
        help="Use local JSONL preview or live Memanto CLI mode.",
    )
    parser.add_argument(
        "--store",
        default=os.environ.get("MEMANTO_SKILLS_STORE", DEFAULT_STORE),
        help="JSONL store path for --backend local.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)

    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("pre", "post"):
        command = subparsers.add_parser(name)
        _add_run_args(command)
        command.add_argument("--transcript")
        command.add_argument("--transcript-file")

    wrapped = subparsers.add_parser("wrap")
    _add_run_args(wrapped)
    wrapped.add_argument("wrapped_command", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    backend = backend_from_args(args)

    if args.command == "wrap":
        if not args.wrapped_command:
            parser.error("provide the command to run after --")
        run = _run_from_args(args)
        command = args.wrapped_command
        if command and command[0] == "--":
            command = command[1:]
        return run_wrapped_command(run, command, backend, args.limit)

    run = _run_from_args(args)
    if args.command == "pre":
        injection = build_injection_block(run, backend, args.limit)
        if injection:
            print(injection)
        return 0

    stored = store_completed_run(run, backend)
    print(f"stored_memories={stored}")
    return 0


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skill", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--metadata", default="{}")


def _run_from_args(args: argparse.Namespace) -> SkillRun:
    return SkillRun(
        skill=args.skill,
        task=args.task,
        files=tuple(args.file),
        transcript=_read_transcript(args),
        cwd=args.cwd,
        metadata=_metadata(args.metadata),
    )


def _read_transcript(args: argparse.Namespace) -> str:
    transcript = getattr(args, "transcript", None)
    transcript_file = getattr(args, "transcript_file", None)
    if transcript:
        return transcript
    if transcript_file:
        return Path(transcript_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty() and getattr(args, "command", "") == "post":
        return sys.stdin.read()
    return ""


def _metadata(raw: str) -> dict[str, str]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--metadata must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def _parse_memanto_recall(output: str) -> list[EngineeringMemory]:
    memories: list[EngineeringMemory] = []
    current_title = ""
    current_content: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Found ") or line.startswith("Completed in"):
            continue
        if line.startswith("ID:") or line.startswith("Type:") or line.startswith("Created:"):
            continue
        if line.startswith("Memory ") or " · memory " in line:
            if current_content:
                memories.append(
                    EngineeringMemory(
                        title=current_title,
                        content=_compact(" ".join(current_content), 600),
                    )
                )
                current_content = []
            continue
        if not current_title:
            current_title = line
            continue
        current_content.append(line)

    if current_content:
        memories.append(
            EngineeringMemory(title=current_title, content=_compact(" ".join(current_content), 600))
        )
    return memories[:DEFAULT_LIMIT]


def _tags_for(run: SkillRun) -> tuple[str, ...]:
    tags = [SOURCE, f"skill:{run.skill}"]
    for file_path in run.files[:8]:
        path = Path(file_path)
        tags.append(f"file:{path.name}")
        if path.parent != Path("."):
            tags.append(f"path:{path.parent.as_posix()}")
    if run.cwd:
        tags.append(f"project:{Path(run.cwd).name}")
    return tuple(dict.fromkeys(tags))


def _title_for(run: SkillRun) -> str:
    compact_task = _compact(run.task, 72)
    return f"{run.skill}: {compact_task}"


def _compact(text: str, max_chars: int = 1200) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3]}..."


def _terms(value: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[a-zA-Z0-9_./:-]+", value)
        if len(term) > 2
    }


def _score(query_terms: set[str], haystack: str) -> int:
    haystack_lower = haystack.lower()
    score = 0
    for term in query_terms:
        if term in haystack_lower:
            score += 3 if "/" in term or ":" in term else 1
    return score


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _self_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "memory.jsonl"
        backend = LocalJsonlBackend(store)
        first = SkillRun(
            skill="grill-with-docs",
            task="Review billing retry architecture",
            files=("src/billing/retries.ts",),
            transcript=(
                "Decision: keep retry delays deterministic in tests. "
                "Preserve idempotency keys across retries."
            ),
            cwd="/repo/payments",
        )
        assert store_completed_run(first, backend) == 1
        second = SkillRun(
            skill="tdd",
            task="Add billing retry tests",
            files=("src/billing/retries.ts",),
            cwd="/repo/payments",
        )
        block = build_injection_block(second, backend, DEFAULT_LIMIT)
        assert "<memanto-engineering-memory>" in block
        assert "deterministic" in block
        assert "idempotency" in block
    return 0


if __name__ == "__main__":
    if os.environ.get("MEMANTO_SKILLS_SELF_CHECK") == "1":
        raise SystemExit(_self_check())
    raise SystemExit(main())

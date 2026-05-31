"""Memanto bridge for command-oriented developer skills.

The module is intentionally dependency-free so maintainers can review and run
the example without API keys. Set MEMANTO_SKILLS_BACKEND=memanto-cli to switch
the same lifecycle hooks to the real Memanto CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}

EXPLICIT_MARKER_RE = re.compile(
    r"^\s*(decision|constraint|preference|gotcha|artifact|followup|error)\s*:\s*(.+)$",
    re.IGNORECASE,
)
FILE_RE = re.compile(r"(?P<file>[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|md|yml|yaml|json))")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_tag(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.:/-]+", "-", value.strip().lower())
    return cleaned.strip("-")[:80]


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


@dataclass(frozen=True)
class SkillRun:
    skill: str
    task: str
    cwd: str
    files: list[str] = field(default_factory=list)

    def query_terms(self) -> list[str]:
        return unique(
            [
                normalize_tag(self.skill),
                *[normalize_tag(part) for part in self.task.split()],
                *[normalize_tag(path) for path in self.files],
                normalize_tag(Path(self.cwd).name),
            ]
        )


@dataclass
class SkillMemory:
    memory_type: str
    content: str
    confidence: float
    source: str
    tags: list[str]
    provenance: str = "inferred"
    created_at: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, object]:
        return {
            "type": self.memory_type,
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "tags": self.tags,
            "provenance": self.provenance,
            "created_at": self.created_at,
        }


@dataclass
class RecalledContext:
    run: SkillRun
    memories: list[SkillMemory]

    def as_env_block(self) -> str:
        if not self.memories:
            return "MEMANTO_CONTEXT: no relevant prior engineering memories found."

        lines = ["MEMANTO_CONTEXT:"]
        for memory in self.memories:
            tags = ", ".join(memory.tags[:5])
            lines.append(
                f"- [{memory.memory_type} {memory.confidence:.2f}] "
                f"{memory.content} ({tags})"
            )
        return "\n".join(lines)


class MemoryBackend(Protocol):
    def recall(self, query_terms: list[str], limit: int = 5) -> list[SkillMemory]:
        """Return relevant memories for a future skill run."""

    def remember(self, memories: list[SkillMemory]) -> None:
        """Persist distilled memories after a skill run."""


class LocalJsonlBackend:
    """Reviewer-safe backend with deterministic scoring."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def recall(self, query_terms: list[str], limit: int = 5) -> list[SkillMemory]:
        query = {term for term in query_terms if term}
        scored: list[tuple[int, SkillMemory]] = []
        for memory in self._read_all():
            haystack = {
                normalize_tag(memory.memory_type),
                *memory.tags,
                *[normalize_tag(part) for part in memory.content.split()],
            }
            score = len(query & haystack)
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def remember(self, memories: list[SkillMemory]) -> None:
        existing = {(m.memory_type, m.content) for m in self._read_all()}
        with self.path.open("a", encoding="utf-8") as handle:
            for memory in memories:
                key = (memory.memory_type, memory.content)
                if key in existing:
                    continue
                handle.write(json.dumps(memory.to_json(), sort_keys=True) + "\n")
                existing.add(key)

    def _read_all(self) -> list[SkillMemory]:
        if not self.path.exists():
            return []

        memories: list[SkillMemory] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            memories.append(
                SkillMemory(
                    memory_type=str(item["type"]),
                    content=str(item["content"]),
                    confidence=float(item["confidence"]),
                    source=str(item["source"]),
                    tags=[str(tag) for tag in item.get("tags", [])],
                    provenance=str(item.get("provenance", "inferred")),
                    created_at=str(item.get("created_at", utc_now())),
                )
            )
        return memories


class MemantoCliBackend:
    """Live backend that routes through the installed Memanto CLI."""

    def __init__(self, command: str = "memanto") -> None:
        self.command = command

    def recall(self, query_terms: list[str], limit: int = 5) -> list[SkillMemory]:
        query = " ".join(query_terms)
        result = subprocess.run(
            [self.command, "recall", query, "--limit", str(limit)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        memories: list[SkillMemory] = []
        for line in result.stdout.splitlines():
            text = line.strip(" -")
            if not text or "Memory ID:" in text:
                continue
            memories.append(
                SkillMemory(
                    memory_type="context",
                    content=text,
                    confidence=0.70,
                    source="memanto-cli",
                    tags=[normalize_tag(term) for term in query_terms[:5]],
                    provenance="retrieved",
                )
            )
            if len(memories) >= limit:
                break
        return memories

    def remember(self, memories: list[SkillMemory]) -> None:
        for memory in memories:
            args = [
                self.command,
                "remember",
                memory.content,
                "--type",
                memory.memory_type,
                "--confidence",
                f"{memory.confidence:.2f}",
                "--source",
                memory.source,
                "--provenance",
                memory.provenance,
            ]
            if memory.tags:
                args.extend(["--tags", ",".join(memory.tags)])
            subprocess.run(args, check=True)


class DecisionTrailTap:
    """Append-only event tap for mid-session skill decisions."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path(".memanto-skill-events.jsonl")
        self.path = path

    def record(
        self,
        kind: str,
        content: str,
        *,
        files: list[str] | None = None,
        skill: str | None = None,
    ) -> None:
        event = {
            "kind": normalize_tag(kind),
            "content": content.strip(),
            "files": files or [],
            "skill": skill,
            "created_at": utc_now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def consume(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        events = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.path.unlink()
        return events


class TranscriptDistiller:
    """Extract typed engineering memories from transcripts and tap events."""

    def distill(
        self,
        run: SkillRun,
        transcript: str,
        events: list[dict[str, object]],
    ) -> list[SkillMemory]:
        memories: list[SkillMemory] = []
        for event in events:
            memories.append(self._memory_from_event(run, event))

        for raw_line in transcript.splitlines():
            line = raw_line.strip(" -*")
            if not line:
                continue

            explicit = EXPLICIT_MARKER_RE.match(line)
            if explicit:
                memory_type = self._type_for_marker(explicit.group(1))
                memories.append(
                    self._build_memory(
                        run,
                        memory_type,
                        explicit.group(2),
                        self._tags_for_line(run, line),
                        0.90,
                        "explicit_marker",
                    )
                )
                continue

            inferred = self._infer_memory(run, line)
            if inferred:
                memories.append(inferred)

        return self._dedupe(memories)

    def _memory_from_event(
        self, run: SkillRun, event: dict[str, object]
    ) -> SkillMemory:
        kind = self._type_for_marker(str(event.get("kind", "observation")))
        content = str(event.get("content", "")).strip()
        files = [str(item) for item in event.get("files", []) if item]
        tags = self._base_tags(run) + [normalize_tag(path) for path in files]
        return self._build_memory(run, kind, content, tags, 0.95, "event_tap")

    def _infer_memory(self, run: SkillRun, line: str) -> SkillMemory | None:
        lowered = line.lower()
        memory_type: str | None = None
        confidence = 0.72

        if "we chose" in lowered or "we decided" in lowered or "decision" in lowered:
            memory_type = "decision"
            confidence = 0.82
        elif "must" in lowered or "do not" in lowered or "never" in lowered:
            memory_type = "instruction"
            confidence = 0.76
        elif "prefer" in lowered or "style" in lowered:
            memory_type = "preference"
        elif "bug" in lowered or "gotcha" in lowered or "risk" in lowered:
            memory_type = "error"
        elif "use " in lowered and any(
            path in lowered for path in ("module", "file", "test")
        ):
            memory_type = "context"

        if memory_type is None:
            return None

        return self._build_memory(
            run,
            memory_type,
            line,
            self._tags_for_line(run, line),
            confidence,
            "heuristic_transcript",
        )

    def _build_memory(
        self,
        run: SkillRun,
        memory_type: str,
        content: str,
        tags: list[str],
        confidence: float,
        provenance: str,
    ) -> SkillMemory:
        if memory_type not in MEMORY_TYPES:
            memory_type = "observation"
        return SkillMemory(
            memory_type=memory_type,
            content=content.strip(),
            confidence=confidence,
            source=f"skill:{run.skill}",
            tags=unique(tags),
            provenance=provenance,
        )

    def _tags_for_line(self, run: SkillRun, line: str) -> list[str]:
        file_tags = [
            normalize_tag(match.group("file")) for match in FILE_RE.finditer(line)
        ]
        word_tags = [
            normalize_tag(part)
            for part in re.findall(r"[A-Za-z][\w-]{3,}", line)
        ]
        return self._base_tags(run) + file_tags + word_tags[:8]

    def _base_tags(self, run: SkillRun) -> list[str]:
        return [
            normalize_tag(f"skill:{run.skill}"),
            normalize_tag(f"cwd:{Path(run.cwd).name}"),
            *[normalize_tag(f"file:{path}") for path in run.files],
        ]

    def _type_for_marker(self, marker: str) -> str:
        normalized = marker.lower()
        if normalized == "constraint":
            return "instruction"
        if normalized == "gotcha":
            return "error"
        if normalized == "followup":
            return "commitment"
        return normalized if normalized in MEMORY_TYPES else "observation"

    def _dedupe(self, memories: list[SkillMemory]) -> list[SkillMemory]:
        seen: set[tuple[str, str]] = set()
        out: list[SkillMemory] = []
        for memory in memories:
            key = (memory.memory_type, re.sub(r"\s+", " ", memory.content.lower()))
            if key in seen:
                continue
            seen.add(key)
            out.append(memory)
        return out


class SkillMemoryBridge:
    """Before/during/after lifecycle adapter for developer skill commands."""

    def __init__(
        self,
        backend: MemoryBackend,
        tap: DecisionTrailTap | None = None,
        distiller: TranscriptDistiller | None = None,
    ) -> None:
        self.backend = backend
        self.tap = tap or DecisionTrailTap()
        self.distiller = distiller or TranscriptDistiller()

    def before_skill(self, run: SkillRun, limit: int = 5) -> RecalledContext:
        return RecalledContext(
            run=run,
            memories=self.backend.recall(run.query_terms(), limit),
        )

    def after_skill(self, run: SkillRun, transcript: str) -> list[SkillMemory]:
        events = self.tap.consume()
        memories = self.distiller.distill(run, transcript, events)
        if memories:
            self.backend.remember(memories)
        return memories


def default_backend() -> MemoryBackend:
    backend = os.getenv("MEMANTO_SKILLS_BACKEND", "local").strip().lower()
    if backend == "memanto-cli":
        return MemantoCliBackend()
    path = Path(os.getenv("MEMANTO_SKILLS_STORE", ".memanto-skills-memory.jsonl"))
    return LocalJsonlBackend(path)


def command_tap(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Record a decision-trail event.")
    parser.add_argument("kind")
    parser.add_argument("content")
    parser.add_argument("--file", dest="files", action="append", default=[])
    parser.add_argument("--skill")
    parser.add_argument("--events", default=".memanto-skill-events.jsonl")
    args = parser.parse_args(argv)

    DecisionTrailTap(Path(args.events)).record(
        args.kind,
        args.content,
        files=args.files,
        skill=args.skill,
    )
    return 0


def command_wrap(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Wrap a skill command.")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--file", dest="files", action="append", default=[])
    parser.add_argument("--transcript", help="Write command output transcript here")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if not args.command:
        parser.error("command is required after --")

    bridge = SkillMemoryBridge(default_backend())
    run = SkillRun(args.skill, args.task, args.cwd, args.files)
    context = bridge.before_skill(run)
    print(context.as_env_block())

    env = os.environ.copy()
    env["MEMANTO_CONTEXT"] = context.as_env_block()
    completed = subprocess.run(
        args.command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    transcript = "\n".join(
        part for part in [completed.stdout, completed.stderr] if part
    )
    if args.transcript:
        Path(args.transcript).write_text(transcript, encoding="utf-8")
    bridge.after_skill(run, transcript)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: skill_memory.py {tap|wrap} ...", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "tap":
        return command_tap(rest)
    if command == "wrap":
        return command_wrap(rest)
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

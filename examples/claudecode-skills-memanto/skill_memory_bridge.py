"""Memanto bridge for command-oriented Claude Code skills.

The example keeps the default backend local and credential-free so reviewers can
run it in CI or a fresh checkout. Set MEMANTO_SKILLS_BACKEND=cli to route writes
and recalls through the installed ``memanto`` CLI instead.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


MEMORY_TYPES = {
    "artifact",
    "commitment",
    "context",
    "decision",
    "error",
    "event",
    "fact",
    "goal",
    "instruction",
    "learning",
    "observation",
    "preference",
    "relationship",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def stable_id(prefix: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "-", prefix.lower()).strip("-")
    return f"{compact[:36]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_/-]*", text.lower())
        if token not in STOPWORDS and len(token) > 1
    }


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass
class MemoryRecord:
    content: str
    memory_type: str = "decision"
    title: str | None = None
    confidence: float = 0.82
    tags: list[str] = field(default_factory=list)
    source: str = "claudecode-skill"
    provenance: str = "skill_lifecycle"
    created_at: str = field(default_factory=utc_now)
    memory_id: str | None = None

    def __post_init__(self) -> None:
        if self.memory_type not in MEMORY_TYPES:
            self.memory_type = "observation"
        self.content = " ".join(self.content.split())
        if not self.title:
            self.title = self.content[:76]
        self.confidence = clamp_confidence(self.confidence)
        self.tags = sorted({tag for tag in self.tags if tag})
        if not self.memory_id:
            self.memory_id = stable_id(self.title or self.memory_type)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "MemoryRecord":
        return cls(
            content=str(payload.get("content", "")),
            memory_type=str(payload.get("memory_type", "observation")),
            title=(
                str(payload["title"])
                if payload.get("title") is not None
                else None
            ),
            confidence=float(payload.get("confidence", 0.72)),
            tags=[str(tag) for tag in payload.get("tags", [])],
            source=str(payload.get("source", "claudecode-skill")),
            provenance=str(payload.get("provenance", "skill_lifecycle")),
            created_at=str(payload.get("created_at", utc_now())),
            memory_id=(
                str(payload["memory_id"])
                if payload.get("memory_id") is not None
                else None
            ),
        )


class MemoryBackend(Protocol):
    def remember(self, memory: MemoryRecord) -> str:
        """Persist one memory and return its id."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[MemoryRecord]:
        """Return the most relevant memories for a prompt."""


class LocalJsonlBackend:
    """Small deterministic backend used for demos and tests."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []

        memories: list[MemoryRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                memories.append(MemoryRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return memories

    def remember(self, memory: MemoryRecord) -> str:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(memory), sort_keys=True) + "\n")
        return memory.memory_id or ""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[MemoryRecord]:
        tag_filter = set(tags or [])
        scored: list[tuple[float, MemoryRecord]] = []
        for memory in self._read_all():
            score = score_memory(memory, query, tag_filter)
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]


class MemantoCliBackend:
    """Thin adapter around the installed Memanto CLI."""

    def __init__(self, executable: str = "memanto") -> None:
        self.executable = executable

    def remember(self, memory: MemoryRecord) -> str:
        cmd = [
            self.executable,
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--title",
            memory.title or memory.content[:50],
            "--confidence",
            str(memory.confidence),
            "--source",
            memory.source,
            "--provenance",
            memory.provenance,
        ]
        if memory.tags:
            cmd.extend(["--tags", ",".join(memory.tags)])
        subprocess.run(cmd, check=True, text=True)
        return memory.memory_id or ""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[MemoryRecord]:
        cmd = [self.executable, "recall", query, "--limit", str(limit)]
        if tags:
            cmd.extend(["--tags", ",".join(tags)])
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        return [
            MemoryRecord(
                content=result.stdout.strip(),
                memory_type="context",
                title="Memanto CLI recall",
                confidence=0.8,
                tags=tags or [],
            )
        ]


def score_memory(
    memory: MemoryRecord,
    query: str,
    tag_filter: set[str] | None = None,
) -> float:
    if tag_filter and not tag_filter.intersection(memory.tags):
        return 0.0

    query_tokens = tokenize(query)
    memory_tokens = tokenize(
        f"{memory.title or ''} {memory.content} {' '.join(memory.tags)}"
    )
    if not query_tokens or not memory_tokens:
        return 0.0

    overlap = query_tokens.intersection(memory_tokens)
    if not overlap:
        return 0.0

    tag_bonus = 0.18 * len(set(memory.tags).intersection(query_tokens))
    type_bonus = 0.2 if memory.memory_type in {"decision", "instruction"} else 0.0
    confidence_bonus = memory.confidence * 0.1
    return (len(overlap) / len(query_tokens)) + tag_bonus + type_bonus + confidence_bonus


def extract_memories(
    text: str,
    *,
    skill_name: str,
    cwd: str | None = None,
    paths: list[str] | None = None,
) -> list[MemoryRecord]:
    """Distill skill output into typed engineering memories."""

    tags = normalize_tags([skill_name, cwd or "", *(paths or [])])
    memories: list[MemoryRecord] = []
    prefix_types = {
        "anti-pattern": "instruction",
        "commitment": "commitment",
        "convention": "instruction",
        "decision": "decision",
        "gotcha": "error",
        "preference": "preference",
        "rule": "instruction",
        "watch": "observation",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue

        prefix_match = re.match(r"^([A-Za-z -]{3,24}):\s+(.+)$", line)
        if prefix_match:
            prefix = prefix_match.group(1).lower()
            content = prefix_match.group(2).strip()
            memory_type = prefix_types.get(prefix)
            if memory_type:
                memories.append(
                    MemoryRecord(
                        content=content,
                        memory_type=memory_type,
                        title=f"{prefix.title()}: {content[:58]}",
                        confidence=0.9,
                        tags=tags,
                    )
                )
            continue

        lowered = line.lower()
        if any(marker in lowered for marker in ("we chose", "we decided", "decision")):
            memories.append(
                MemoryRecord(
                    content=line,
                    memory_type="decision",
                    confidence=0.78,
                    tags=tags,
                )
            )
        elif lowered.startswith(("prefer ", "keep ", "avoid ", "do not ", "must ")):
            memories.append(
                MemoryRecord(
                    content=line,
                    memory_type="instruction",
                    confidence=0.76,
                    tags=tags,
                )
            )

    if paths:
        memories.append(
            MemoryRecord(
                content=(
                    f"{skill_name} touched {', '.join(paths)}. "
                    "Use these paths as retrieval anchors for related future skills."
                ),
                memory_type="context",
                title=f"{skill_name} touched project paths",
                confidence=0.7,
                tags=tags,
            )
        )

    return dedupe_memories(memories)


def dedupe_memories(memories: list[MemoryRecord]) -> list[MemoryRecord]:
    seen: set[str] = set()
    deduped: list[MemoryRecord] = []
    for memory in memories:
        key = memory.content.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(memory)
    return deduped


def normalize_tags(values: list[str]) -> list[str]:
    tags: set[str] = set()
    for value in values:
        for part in re.split(r"[,;\s]+", value):
            tag = re.sub(r"[^a-z0-9_/-]+", "-", part.lower()).strip("-")
            if tag and len(tag) <= 48:
                tags.add(tag)
    return sorted(tags)


def render_context(memories: list[MemoryRecord]) -> str:
    if not memories:
        return "MEMANTO_CONTEXT: no relevant memories found."

    lines = ["MEMANTO_CONTEXT:"]
    for memory in memories:
        tags = f" tags={','.join(memory.tags)}" if memory.tags else ""
        lines.append(
            "- "
            f"[{memory.memory_type}; confidence={memory.confidence:.2f}{tags}] "
            f"{memory.content}"
        )
    return "\n".join(lines)


class SkillMemoryBridge:
    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def before_skill(
        self,
        *,
        skill_name: str,
        prompt: str,
        cwd: str | None = None,
        paths: list[str] | None = None,
        limit: int = 5,
    ) -> str:
        query = " ".join([skill_name, prompt, cwd or "", " ".join(paths or [])])
        tags = normalize_tags([skill_name, *(paths or [])])
        memories = self.backend.recall(query, limit=limit, tags=tags or None)
        if not memories:
            memories = self.backend.recall(query, limit=limit)
        return render_context(memories)

    def after_skill(
        self,
        *,
        skill_name: str,
        summary: str,
        transcript: str = "",
        cwd: str | None = None,
        paths: list[str] | None = None,
    ) -> list[MemoryRecord]:
        distilled = extract_memories(
            f"{summary}\n{transcript}",
            skill_name=skill_name,
            cwd=cwd,
            paths=paths,
        )
        for memory in distilled:
            self.backend.remember(memory)
        return distilled


def create_backend() -> MemoryBackend:
    backend_name = os.getenv("MEMANTO_SKILLS_BACKEND", "local").lower()
    if backend_name == "cli":
        return MemantoCliBackend(os.getenv("MEMANTO_BIN", "memanto"))

    memory_file = os.getenv(
        "MEMANTO_SKILLS_MEMORY_FILE",
        str(Path.cwd() / ".memanto-skills-memory.jsonl"),
    )
    return LocalJsonlBackend(memory_file)


def read_text_argument(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return value


def parse_paths(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="Print recall context for a skill")
    before.add_argument("--skill", required=True)
    before.add_argument("--prompt", required=True)
    before.add_argument("--cwd", default=None)
    before.add_argument("--paths", default=None)
    before.add_argument("--limit", type=int, default=5)

    after = subparsers.add_parser("after", help="Store memories from a skill result")
    after.add_argument("--skill", required=True)
    after.add_argument("--summary", required=True)
    after.add_argument("--transcript", default="")
    after.add_argument("--cwd", default=None)
    after.add_argument("--paths", default=None)

    wrap = subparsers.add_parser("wrap", help="Run a command with memory capture")
    wrap.add_argument("--skill", required=True)
    wrap.add_argument("--prompt", required=True)
    wrap.add_argument("--cwd", default=None)
    wrap.add_argument("--paths", default=None)
    wrap.add_argument("cmd", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = SkillMemoryBridge(create_backend())
    paths = parse_paths(getattr(args, "paths", None))

    if args.command == "before":
        print(
            bridge.before_skill(
                skill_name=args.skill,
                prompt=read_text_argument(args.prompt),
                cwd=args.cwd,
                paths=paths,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "after":
        memories = bridge.after_skill(
            skill_name=args.skill,
            summary=read_text_argument(args.summary),
            transcript=read_text_argument(args.transcript),
            cwd=args.cwd,
            paths=paths,
        )
        print(json.dumps([asdict(memory) for memory in memories], indent=2))
        return 0

    if args.command == "wrap":
        if not args.cmd:
            print("wrap requires a command after --", file=sys.stderr)
            return 2
        print(
            bridge.before_skill(
                skill_name=args.skill,
                prompt=args.prompt,
                cwd=args.cwd,
                paths=paths,
            )
        )
        result = subprocess.run(args.cmd, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        bridge.after_skill(
            skill_name=args.skill,
            summary=(
                f"Observation: Command exited with {result.returncode}. "
                "Review stdout/stderr for any decisions or errors."
            ),
            transcript=f"{result.stdout}\n{result.stderr}",
            cwd=args.cwd,
            paths=paths,
        )
        return result.returncode

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

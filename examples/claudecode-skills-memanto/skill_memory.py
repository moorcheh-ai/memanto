"""Cross-skill memory hooks for Claude Code-style developer skills.

The module is intentionally dependency-free so maintainers can run and review
the example without a Moorcheh API key. Set ``MEMANTO_SKILL_BACKEND=cli`` and
``MOORCHEH_API_KEY`` to route writes and recalls through the installed
``memanto`` command instead of the local JSONL preview backend.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

DEFAULT_STORE = Path(".memanto-skills/memories.jsonl")
MEMORY_PREFIXES: tuple[tuple[str, str, float], ...] = (
    ("decision:", "decision", 0.9),
    ("preference:", "preference", 0.86),
    ("instruction:", "instruction", 0.88),
    ("constraint:", "instruction", 0.82),
    ("context:", "context", 0.72),
    ("artifact:", "artifact", 0.68),
)
SKILL_NAMES = ("/grill-with-docs", "/tdd", "/handoff")


@dataclass(frozen=True)
class Memory:
    """A distilled engineering memory carried between skill executions."""

    text: str
    memory_type: str
    source_skill: str
    path: str
    confidence: float
    created_at: str


class MemoryBackend(Protocol):
    """Storage contract shared by the local preview and live Memanto backends."""

    def remember(self, memory: Memory) -> None:
        """Persist one memory."""

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        """Return memories relevant to a new skill invocation."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_./-]{3,}", value.lower()))


class LocalJsonlBackend:
    """Credential-free backend used for reviewer demos and unit tests."""

    def __init__(self, store_path: Path = DEFAULT_STORE) -> None:
        self.store_path = store_path

    def remember(self, memory: Memory) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {self._dedupe_key(item) for item in self._read_all()}
        if self._dedupe_key(memory) in existing:
            return
        with self.store_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(memory), sort_keys=True) + "\n")

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        query_terms = tokenize(query)
        ranked: list[tuple[float, Memory]] = []
        for memory in self._read_all():
            haystack = " ".join(
                [memory.text, memory.memory_type, memory.source_skill, memory.path]
            )
            overlap = len(query_terms & tokenize(haystack))
            if overlap == 0:
                continue
            type_boost = (
                0.35 if memory.memory_type in {"decision", "instruction"} else 0
            )
            ranked.append((overlap + type_boost + memory.confidence, memory))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]

    def _read_all(self) -> list[Memory]:
        if not self.store_path.exists():
            return []
        memories: list[Memory] = []
        with self.store_path.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                memories.append(Memory(**json.loads(line)))
        return memories

    @staticmethod
    def _dedupe_key(memory: Memory) -> tuple[str, str, str]:
        return (
            normalize_text(memory.text).lower(),
            memory.memory_type,
            memory.path,
        )


class MemantoCliBackend:
    """Live backend that delegates to the installed ``memanto`` CLI."""

    def __init__(self, command: str = "memanto") -> None:
        self.command = command

    def remember(self, memory: Memory) -> None:
        payload = (
            f"{memory.text}\n\n"
            f"source_skill={memory.source_skill}; path={memory.path}; "
            f"confidence={memory.confidence:.2f}"
        )
        subprocess.run(
            [self.command, "remember", payload, "--type", memory.memory_type],
            check=True,
            text=True,
        )

    def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        result = subprocess.run(
            [self.command, "recall", query, "--limit", str(limit)],
            check=True,
            capture_output=True,
            text=True,
        )
        text = normalize_text(result.stdout)
        if not text:
            return []
        return [
            Memory(
                text=text,
                memory_type="context",
                source_skill="memanto recall",
                path="",
                confidence=0.75,
                created_at=utc_now(),
            )
        ]


class SkillMemoryBridge:
    """Captures skill outputs and injects relevant memories before new runs."""

    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def before_skill(self, skill: str, prompt: str, cwd: Path) -> str:
        query = f"{skill} {cwd} {prompt}"
        memories = self.backend.recall(query)
        if not memories:
            return ""
        bullets = "\n".join(f"- [{item.memory_type}] {item.text}" for item in memories)
        return (
            "Relevant Memanto engineering memory for this skill run:\n"
            f"{bullets}\n"
            "Apply these constraints unless the user explicitly overrides them."
        )

    def after_skill(self, skill: str, transcript: str, cwd: Path) -> list[Memory]:
        memories = distill_memories(transcript, source_skill=skill, cwd=cwd)
        for memory in memories:
            self.backend.remember(memory)
        return memories


def distill_memories(transcript: str, *, source_skill: str, cwd: Path) -> list[Memory]:
    """Extract explicit durable engineering signals from a skill transcript."""

    memories: list[Memory] = []
    for raw_line in transcript.splitlines():
        line = normalize_text(raw_line)
        lowered = line.lower()
        for prefix, memory_type, confidence in MEMORY_PREFIXES:
            if lowered.startswith(prefix):
                memories.append(
                    Memory(
                        text=line[len(prefix) :].strip(),
                        memory_type=memory_type,
                        source_skill=source_skill,
                        path=str(cwd),
                        confidence=confidence,
                        created_at=utc_now(),
                    )
                )
                break
    return memories


def build_backend() -> MemoryBackend:
    backend = os.getenv("MEMANTO_SKILL_BACKEND", "local").lower()
    if backend == "cli":
        return MemantoCliBackend(os.getenv("MEMANTO_COMMAND", "memanto"))
    return LocalJsonlBackend(Path(os.getenv("MEMANTO_SKILL_STORE", str(DEFAULT_STORE))))


def print_injected_context(context: str) -> None:
    if context:
        print(context)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="Recall and print memory context")
    before.add_argument("--skill", required=True, choices=SKILL_NAMES)
    before.add_argument("--prompt", default="")
    before.add_argument("--cwd", type=Path, default=Path.cwd())

    after = subparsers.add_parser("after", help="Distill and store skill transcript")
    after.add_argument("--skill", required=True, choices=SKILL_NAMES)
    after.add_argument("--transcript-file", type=Path, required=True)
    after.add_argument("--cwd", type=Path, default=Path.cwd())

    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    bridge = SkillMemoryBridge(build_backend())

    if args.command == "before":
        print_injected_context(bridge.before_skill(args.skill, args.prompt, args.cwd))
        return 0

    transcript = args.transcript_file.read_text(encoding="utf-8")
    memories = bridge.after_skill(args.skill, transcript, args.cwd)
    print(f"stored {len(memories)} memories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

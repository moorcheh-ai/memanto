"""Memanto memory bridge for Claude Code / mattpocock-style skills.

The module wraps separate skill executions with three steps:

1. recall relevant engineering memories before the command starts,
2. inject those memories into the child process environment, and
3. distill durable decisions from the completed transcript.

It ships with a local JSONL backend so reviewers can run the example without
Moorcheh credentials. Set ``MEMANTO_SKILLS_BACKEND=cli`` to use the real
``memanto`` command-line client.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_AGENT_ID = "claudecode-skills"
DEFAULT_MEMORY_FILE = Path(".memanto-skills-memory.jsonl")


@dataclass(frozen=True)
class Memory:
    content: str
    memory_type: str = "decision"
    confidence: float = 0.8
    source: str = DEFAULT_AGENT_ID
    tags: tuple[str, ...] = ()
    created_at: float = 0.0

    def to_json(self) -> str:
        data = asdict(self)
        data["tags"] = list(self.tags)
        data["created_at"] = self.created_at or time.time()
        return json.dumps(data, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> Memory:
        data = json.loads(line)
        return cls(
            content=data["content"],
            memory_type=data.get("memory_type", "decision"),
            confidence=float(data.get("confidence", 0.8)),
            source=data.get("source", DEFAULT_AGENT_ID),
            tags=tuple(data.get("tags", [])),
            created_at=float(data.get("created_at", 0.0)),
        )


class MemoryBackend(Protocol):
    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        """Return memories relevant to *query*."""

    def remember(self, memory: Memory) -> None:
        """Store one memory."""


class LocalJsonlBackend:
    """Credential-free backend used for tests, demos, and offline review."""

    def __init__(self, path: Path = DEFAULT_MEMORY_FILE) -> None:
        self.path = path

    def _load(self) -> list[Memory]:
        if not self.path.exists():
            return []
        memories: list[Memory] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                memories.append(Memory.from_json(line))
        return memories

    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        query_terms = _tokenize(query)
        scored: list[tuple[float, Memory]] = []
        for memory in self._load():
            haystack = _tokenize(" ".join([memory.content, *memory.tags]))
            overlap = len(query_terms & haystack)
            if overlap:
                scored.append((overlap + memory.confidence, memory))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def remember(self, memory: Memory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {item.content for item in self._load()}
        if memory.content in existing:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(memory.to_json() + "\n")


class MemantoCliBackend:
    """Backend that talks to the real Memanto CLI."""

    def __init__(self, agent_id: str = DEFAULT_AGENT_ID) -> None:
        self.agent_id = agent_id
        self._ensure_agent()

    def _ensure_agent(self) -> None:
        activate = subprocess.run(
            ["memanto", "agent", "activate", self.agent_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if activate.returncode == 0:
            return
        subprocess.run(["memanto", "agent", "create", self.agent_id], check=True)

    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        if not output:
            return []
        return [
            Memory(
                content=output,
                memory_type="context",
                confidence=0.7,
                source=self.agent_id,
                tags=("memanto-cli",),
            )
        ]

    def remember(self, memory: Memory) -> None:
        cmd = [
            "memanto",
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--confidence",
            str(memory.confidence),
            "--provenance",
            "agent_observation",
            "--source",
            self.agent_id,
        ]
        if memory.tags:
            cmd.extend(["--tags", ",".join(memory.tags)])
        subprocess.run(cmd, check=True)


class TranscriptDistiller:
    """Extract stable engineering preferences from skill transcripts."""

    PATTERNS: tuple[tuple[str, str, float], ...] = (
        (r"\b(?:decision|decided|we will|use|prefer)\b[:\s-]+(.+)", "decision", 0.88),
        (r"\b(?:convention|preference)\b[:\s-]+(.+)", "preference", 0.82),
        (r"\b(?:must|always|never|avoid)\b[:\s-]+(.+)", "instruction", 0.9),
        (r"\b(?:quirk|caveat|gotcha)\b[:\s-]+(.+)", "observation", 0.72),
    )

    def distill(self, skill_name: str, transcript: str) -> list[Memory]:
        memories: list[Memory] = []
        seen: set[str] = set()
        for raw_line in transcript.splitlines():
            line = raw_line.strip(" -\t")
            if not line:
                continue
            for pattern, memory_type, confidence in self.PATTERNS:
                match = re.search(pattern, line, flags=re.IGNORECASE)
                if not match:
                    continue
                content = _clean_sentence(match.group(1))
                if len(content) < 12 or content.lower() in seen:
                    continue
                seen.add(content.lower())
                memories.append(
                    Memory(
                        content=content,
                        memory_type=memory_type,
                        confidence=confidence,
                        source=skill_name,
                        tags=("claude-code", "skills", skill_name),
                    )
                )
                break
        return memories


class SkillMemoryBridge:
    def __init__(
        self,
        backend: MemoryBackend,
        distiller: TranscriptDistiller | None = None,
    ) -> None:
        self.backend = backend
        self.distiller = distiller or TranscriptDistiller()

    def build_context(self, skill_name: str, task: str, limit: int = 6) -> str:
        query = f"claude-code skills {skill_name} {task}"
        memories = self.backend.recall(query, limit=limit)
        if not memories:
            return ""
        lines = ["Relevant Memanto memories:"]
        for memory in memories:
            lines.append(f"- [{memory.memory_type}] {memory.content}")
        return "\n".join(lines)

    def run(self, skill_name: str, command: list[str], task: str = "") -> int:
        context = self.build_context(skill_name, task or " ".join(command))
        env = os.environ.copy()
        if context:
            env["MEMANTO_SKILL_CONTEXT"] = context
            print(context)
            print()

        completed = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)

        # Distill only the child skill transcript. Re-storing injected context
        # would create duplicate memories on every wrapped execution.
        transcript = "\n".join([completed.stdout, completed.stderr])
        for memory in self.distiller.distill(skill_name, transcript):
            self.backend.remember(memory)
        return completed.returncode


def backend_from_env() -> MemoryBackend:
    backend = os.getenv("MEMANTO_SKILLS_BACKEND", "local").lower()
    if backend == "cli":
        return MemantoCliBackend(os.getenv("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID))
    if backend != "local":
        raise ValueError("MEMANTO_SKILLS_BACKEND must be 'local' or 'cli'")
    path = Path(os.getenv("MEMANTO_SKILLS_MEMORY_FILE", str(DEFAULT_MEMORY_FILE)))
    return LocalJsonlBackend(path)


def _tokenize(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value)}


def _clean_sentence(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1].upper() + value[1:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a skill with Memanto memory.")
    parser.add_argument("skill", help="Skill name, for example grill-with-docs")
    parser.add_argument("--task", default="", help="Task text used for memory recall")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("provide a command after --")

    bridge = SkillMemoryBridge(backend_from_env())
    return bridge.run(args.skill, command, task=args.task)


if __name__ == "__main__":
    raise SystemExit(main())

"""Reusable Memanto memory hooks for developer skill workflows.

The module keeps the integration small on purpose:

- local preview mode is deterministic and credential-free for reviewers
- Memanto CLI mode can be used when the developer has already configured the
  standard `memanto` command with Moorcheh credentials
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol


MEMORY_ENV = "MEMANTO_SKILLS_MEMORY"
BACKEND_ENV = "MEMANTO_SKILLS_BACKEND"


@dataclass
class MemoryRecord:
    text: str
    skill_name: str
    task: str
    files: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MemoryStore(Protocol):
    def remember(self, record: MemoryRecord) -> None:
        """Persist a durable engineering memory."""

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Return memories relevant to the current skill invocation."""


class LocalPreviewMemoryStore:
    """JSONL-backed local memory store used for credential-free review."""

    def __init__(self, path: str | Path | None = None) -> None:
        default_path = Path(".memanto-preview") / "skills-memory.jsonl"
        self.path = Path(path or os.getenv(MEMORY_ENV, default_path))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, record: MemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        query_terms = _tokens(query)
        scored: list[tuple[int, MemoryRecord]] = []
        for record in self._records():
            haystack = " ".join([record.text, record.task, *record.files])
            score = len(query_terms & _tokens(haystack))
            if score:
                scored.append((score, record))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [record for _, record in scored[:limit]]

    def _records(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []

        records: list[MemoryRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                records.append(MemoryRecord(**payload))
        return records


class MemantoCliMemoryStore:
    """Adapter for an already configured Memanto CLI environment."""

    def remember(self, record: MemoryRecord) -> None:
        text = _format_record(record)
        subprocess.run(
            ["memanto", "remember", text, "--type", "decision"],
            check=True,
            text=True,
            capture_output=True,
        )

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            check=True,
            text=True,
            capture_output=True,
        )
        memories = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if text:
                memories.append(
                    MemoryRecord(text=text, skill_name="memanto-cli", task=query)
                )
        return memories[:limit]


class SkillMemoryHook:
    """Lifecycle hook that bridges skill execution and durable memory."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def before_skill(
        self,
        skill_name: str,
        task: str,
        files: Iterable[str] = (),
        limit: int = 5,
    ) -> str:
        query = " ".join([skill_name, task, *files])
        memories = self.store.recall(query, limit=limit)
        if not memories:
            return ""

        bullets = "\n".join(f"- {memory.text}" for memory in memories)
        return (
            "Relevant prior engineering memory from Memanto:\n"
            f"{bullets}\n\n"
            "Use these as constraints unless the current task explicitly changes them."
        )

    def after_skill(
        self,
        skill_name: str,
        task: str,
        transcript: str,
        files: Iterable[str] = (),
        explicit_memories: Iterable[str] = (),
    ) -> list[MemoryRecord]:
        memories = [
            *explicit_memories,
            *distill_engineering_memories(transcript),
        ]
        unique_memories = _dedupe(memory.strip() for memory in memories if memory.strip())

        records = [
            MemoryRecord(
                text=memory,
                skill_name=skill_name,
                task=task,
                files=list(files),
            )
            for memory in unique_memories
        ]
        for record in records:
            self.store.remember(record)
        return records

    def run_skill_command(
        self,
        skill_name: str,
        command: list[str],
        task: str,
        files: Iterable[str] = (),
    ) -> subprocess.CompletedProcess[str]:
        context_block = self.before_skill(skill_name, task, files)
        env = os.environ.copy()
        if context_block:
            env["MEMANTO_SKILL_CONTEXT"] = context_block

        result = subprocess.run(command, text=True, capture_output=True, env=env)
        transcript = "\n".join(
            [
                f"$ {shlex.join(command)}",
                result.stdout,
                result.stderr,
            ]
        )
        self.after_skill(skill_name, task, transcript, files)
        return result


def build_memory_store() -> MemoryStore:
    backend = os.getenv(BACKEND_ENV, "local-preview").strip().lower()
    if backend == "memanto-cli":
        return MemantoCliMemoryStore()
    return LocalPreviewMemoryStore()


def distill_engineering_memories(transcript: str) -> list[str]:
    """Extract durable facts from a skill transcript without an LLM dependency."""

    memories: list[str] = []
    patterns = [
        r"^(?:Decision|Architecture|Constraint|Preference|Handoff|Validation):\s*(.+)$",
        r"^- \[(?:decision|constraint|preference|handoff|validation)\]\s*(.+)$",
    ]
    for line in transcript.splitlines():
        clean_line = line.strip()
        for pattern in patterns:
            match = re.match(pattern, clean_line, flags=re.IGNORECASE)
            if match:
                memories.append(match.group(1).strip())

    if not memories:
        summary = _first_meaningful_sentence(transcript)
        if summary:
            memories.append(summary)

    return memories[:8]


def _format_record(record: MemoryRecord) -> str:
    file_label = ", ".join(record.files) if record.files else "no files"
    return (
        f"{record.text}\n"
        f"Source skill: {record.skill_name}\n"
        f"Task: {record.task}\n"
        f"Files: {file_label}"
    )


def _first_meaningful_sentence(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) > 30 and not line.startswith("$ "):
            return line[:240]
    return ""


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_./-]+", text.lower())
        if len(token) > 2
    }


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


__all__ = [
    "LocalPreviewMemoryStore",
    "MemantoCliMemoryStore",
    "MemoryRecord",
    "SkillMemoryHook",
    "build_memory_store",
    "distill_engineering_memories",
]


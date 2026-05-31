"""Lifecycle bridge between developer skills and Memanto."""

from __future__ import annotations

import re
from dataclasses import dataclass

from memory_backends import BaseMemoryBackend


MEMORY_LINE = re.compile(
    r"^(Decision|Preference|Quirk|Constraint|Learning):\s*(.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)


@dataclass
class SkillRun:
    skill_name: str
    task: str
    file_paths: list[str]


class SkillMemoryBridge:
    """Adds recall-before and remember-after hooks to skill execution."""

    def __init__(self, memory: BaseMemoryBackend) -> None:
        self.memory = memory

    def before_skill(self, run: SkillRun, *, limit: int = 6) -> str:
        query = self._query_for(run)
        memories = self.memory.recall(query, limit=limit)
        if not memories:
            return "MEMANTO ENGINEERING MEMORY\n- No relevant memories found."
        lines = ["MEMANTO ENGINEERING MEMORY"]
        lines.extend(f"- {memory}" for memory in memories)
        return "\n".join(lines)

    def after_skill(self, run: SkillRun, transcript: str) -> list[str]:
        stored: list[str] = []
        for label, value in MEMORY_LINE.findall(transcript):
            memory = f"{label.title()}: {value.strip()}"
            memory_type = self._memory_type(label)
            tags = ",".join(["claudecode", "skills", run.skill_name.strip("/")])
            self.memory.remember(memory, memory_type=memory_type, tags=tags)
            stored.append(memory)
        return stored

    def _query_for(self, run: SkillRun) -> str:
        path_text = " ".join(run.file_paths)
        return f"{run.skill_name} {run.task} {path_text}"

    def _memory_type(self, label: str) -> str:
        normalized = label.lower()
        if normalized == "decision":
            return "decision"
        if normalized == "preference":
            return "preference"
        if normalized in {"quirk", "constraint"}:
            return "context"
        return "learning"


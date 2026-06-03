"""Lifecycle bridge between developer skills and Memanto."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from memory_backends import BaseMemoryBackend

MEMORY_LINE = re.compile(
    r"^\s*(Decision|Preference|Quirk|Constraint|Learning):\s*(.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)


@dataclass
class SkillRun:
    """Metadata about one isolated developer skill execution."""

    skill_name: str
    task: str
    file_paths: list[str]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class SkillExecution:
    """Result returned when the bridge wraps an arbitrary skill runner."""

    prompt: str
    transcript: str
    stored_memories: list[str]


class SkillMemoryBridge:
    """Drop-in recall-before and remember-after hooks for skill execution."""

    def __init__(
        self,
        memory: BaseMemoryBackend,
        *,
        header: str = "MEMANTO ENGINEERING MEMORY",
        base_tags: tuple[str, ...] = ("claudecode", "skills"),
    ) -> None:
        """Create a bridge around any compatible memory backend."""
        self.memory = memory
        self.header = header
        self.base_tags = base_tags

    def before_skill(self, run: SkillRun, *, limit: int = 6) -> str:
        """Format relevant recalled memories for injection into a skill prompt."""
        query = self._query_for(run)
        memories = self.memory.recall(query, limit=limit)
        if not memories:
            return f"{self.header}\n- No relevant memories found."
        lines = [self.header]
        lines.extend(f"- {memory}" for memory in memories)
        return "\n".join(lines)

    def prompt_with_memory(
        self,
        run: SkillRun,
        original_prompt: str,
        *,
        limit: int = 6,
    ) -> str:
        """Return a skill prompt prefixed with recalled engineering memory."""
        memory_context = self.before_skill(run, limit=limit)
        prompt = original_prompt.strip()
        if not prompt:
            return memory_context
        return f"{memory_context}\n\n{prompt}"

    def run_with_memory(
        self,
        run: SkillRun,
        original_prompt: str,
        executor: Callable[[str], str],
        *,
        limit: int = 6,
    ) -> SkillExecution:
        """Wrap any skill runner callable with Memanto memory hooks."""
        prompt = self.prompt_with_memory(run, original_prompt, limit=limit)
        transcript = executor(prompt)
        stored_memories = self.after_skill(run, transcript)
        return SkillExecution(
            prompt=prompt,
            transcript=transcript,
            stored_memories=stored_memories,
        )

    def after_skill(self, run: SkillRun, transcript: str) -> list[str]:
        """Extract labeled durable memories from a completed skill transcript."""
        stored: list[str] = []
        for label, value in MEMORY_LINE.findall(transcript):
            memory = f"{label.title()}: {value.strip()}"
            memory_type = self._memory_type(label)
            tags = ",".join(self._tags_for(run))
            self.memory.remember(memory, memory_type=memory_type, tags=tags)
            stored.append(memory)
        return stored

    def _query_for(self, run: SkillRun) -> str:
        """Build a compact recall query from skill metadata."""
        path_text = " ".join(run.file_paths)
        metadata_text = " ".join(f"{key}:{value}" for key, value in run.metadata.items())
        return f"{run.skill_name} {run.task} {path_text} {metadata_text}"

    def _tags_for(self, run: SkillRun) -> tuple[str, ...]:
        """Build stable tags for memories emitted by one skill run."""
        skill_tag = self._sanitize_tag(run.skill_name)
        if skill_tag:
            return (*self.base_tags, skill_tag)
        return self.base_tags

    def _sanitize_tag(self, value: str) -> str:
        """Normalize user-facing skill names into comma-safe memory tags."""
        normalized = re.sub(r"[\s,/]+", "-", value.strip())
        return normalized.strip("-")

    def _memory_type(self, label: str) -> str:
        """Map a transcript label to Memanto's memory type vocabulary."""
        normalized = label.lower()
        if normalized == "decision":
            return "decision"
        if normalized == "preference":
            return "preference"
        if normalized in {"quirk", "constraint"}:
            return "context"
        return "learning"

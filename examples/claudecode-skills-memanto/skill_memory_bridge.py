"""
Memanto bridge for command-oriented developer skills.

The example is intentionally usable without credentials. LocalJsonlBackend gives
reviewers a deterministic way to run the workflow, while MemantoCliBackend shows
the same lifecycle against an active `memanto` CLI session.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

MEMORY_TYPES = {
    "decision",
    "preference",
    "instruction",
    "artifact",
    "learning",
    "context",
    "observation",
    "error",
}

DECISION_MARKERS = (
    "decide",
    "decision",
    "chosen",
    "we will",
    "use ",
    "prefer",
    "avoid",
    "because",
    "gotcha",
    "bug",
    "constraint",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_./-]+", text.lower()) if len(token) > 2}


@dataclass
class MemoryRecord:
    memory_type: str
    title: str
    content: str
    confidence: float = 0.8
    tags: list[str] = field(default_factory=list)
    source: str = "claudecode-skills-memanto"
    provenance: str = "derived_from_skill_event"
    created_at: str = field(default_factory=utc_now)
    memory_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if self.memory_type not in MEMORY_TYPES:
            msg = f"Unsupported memory type: {self.memory_type}"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)


@dataclass
class SkillEvent:
    kind: str
    text: str
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.8
    created_at: str = field(default_factory=utc_now)


@dataclass
class SkillRun:
    skill_name: str
    prompt: str
    cwd: str
    files: list[str]
    run_id: str = field(default_factory=lambda: str(uuid4()))
    events: list[SkillEvent] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    recalled_memories: list[MemoryRecord] = field(default_factory=list)


class MemoryBackend(Protocol):
    def remember(self, memory: MemoryRecord) -> None:
        """Persist a memory."""

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Return relevant memories for a query."""


class LocalJsonlBackend:
    """Credential-free local backend used by the demo and tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: MemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(memory), sort_keys=True) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        query_tokens = normalize_tokens(query)
        scored: list[tuple[float, MemoryRecord]] = []

        for memory in self._load():
            haystack = " ".join([memory.title, memory.content, " ".join(memory.tags)])
            memory_tokens = normalize_tokens(haystack)
            overlap = len(query_tokens & memory_tokens)
            if overlap == 0:
                continue
            type_boost = 1.5 if memory.memory_type in {"decision", "instruction"} else 1.0
            score = overlap * type_boost + memory.confidence
            scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def _load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []

        records: list[MemoryRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(MemoryRecord(**json.loads(line)))
        return records


class MemantoCliBackend:
    """
    Backend that uses an already configured Memanto CLI.

    It expects callers to run `memanto agent activate <agent-id>` first. The CLI
    owns credentials and active-session state, so this adapter never handles API
    keys directly.
    """

    def __init__(self, memanto_bin: str = "memanto") -> None:
        self.memanto_bin = memanto_bin

    def remember(self, memory: MemoryRecord) -> None:
        command = [
            self.memanto_bin,
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--title",
            memory.title,
            "--confidence",
            str(memory.confidence),
            "--tags",
            ",".join(memory.tags),
            "--source",
            memory.source,
            "--provenance",
            memory.provenance,
        ]
        subprocess.run(command, check=True)

    def recall(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        command = [self.memanto_bin, "recall", query, "--limit", str(limit)]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return [
            MemoryRecord(
                memory_type="context",
                title="Memanto CLI recall",
                content=result.stdout.strip(),
                confidence=0.7,
                tags=["memanto-cli", "recall"],
                provenance="cli_recall_output",
            )
        ]


class SkillMemoryBridge:
    """Lifecycle hook that recalls, taps mid-session events, and persists them."""

    def __init__(self, backend: MemoryBackend, project_slug: str) -> None:
        self.backend = backend
        self.project_slug = project_slug

    def begin_skill(
        self,
        skill_name: str,
        prompt: str,
        cwd: str,
        files: list[str] | None = None,
    ) -> SkillRun:
        files = files or []
        query = self._query_for(skill_name, prompt, cwd, files)
        recalled = self.backend.recall(query, limit=5)
        return SkillRun(
            skill_name=skill_name,
            prompt=prompt,
            cwd=cwd,
            files=files,
            recalled_memories=recalled,
        )

    def record_event(
        self,
        run: SkillRun,
        kind: str,
        text: str,
        files: list[str] | None = None,
        tags: list[str] | None = None,
        confidence: float = 0.8,
    ) -> None:
        run.events.append(
            SkillEvent(
                kind=kind,
                text=text.strip(),
                files=files or [],
                tags=tags or [],
                confidence=confidence,
            )
        )

    def end_skill(self, run: SkillRun, output_summary: str) -> list[MemoryRecord]:
        memories: list[MemoryRecord] = []
        for event in run.events:
            memory = self._event_to_memory(run, event)
            if memory:
                self.backend.remember(memory)
                memories.append(memory)

        summary = MemoryRecord(
            memory_type="artifact",
            title=f"{run.skill_name} output summary",
            content=(
                f"Skill `{run.skill_name}` ran in `{run.cwd}` for project "
                f"`{self.project_slug}`. Summary: {output_summary.strip()}"
            ),
            confidence=0.75,
            tags=[self.project_slug, run.skill_name, "skill-summary"],
            provenance="skill_completion_summary",
        )
        self.backend.remember(summary)
        memories.append(summary)
        return memories

    def context_block(self, run: SkillRun) -> str:
        if not run.recalled_memories:
            return "MEMANTO_CONTEXT: no relevant cross-session memories found."

        lines = ["MEMANTO_CONTEXT:"]
        for memory in run.recalled_memories:
            tags = ", ".join(memory.tags) if memory.tags else "untagged"
            lines.append(
                f"- [{memory.memory_type}] {memory.title} "
                f"(confidence={memory.confidence:.2f}, tags={tags})"
            )
            lines.append(f"  {memory.content}")
        return "\n".join(lines)

    def _event_to_memory(
        self, run: SkillRun, event: SkillEvent
    ) -> MemoryRecord | None:
        if not event.text:
            return None

        event_type = self._classify_event(event)
        if event.kind == "tool_output" and not self._is_memory_worthy(event.text):
            return None

        files = ", ".join(event.files or run.files)
        file_part = f" Files: {files}." if files else ""
        content = (
            f"During `{run.skill_name}` in `{run.cwd}`, "
            f"{event.kind} captured: {event.text}.{file_part}"
        )
        tags = sorted(
            {
                self.project_slug,
                run.skill_name,
                event.kind,
                *event.tags,
                *[Path(file).name for file in event.files],
            }
        )

        return MemoryRecord(
            memory_type=event_type,
            title=self._title_from(event),
            content=content,
            confidence=event.confidence,
            tags=tags,
        )

    def _classify_event(self, event: SkillEvent) -> str:
        text = event.text.lower()
        if event.kind in {"decision", "constraint", "preference", "error"}:
            return {
                "decision": "decision",
                "constraint": "instruction",
                "preference": "preference",
                "error": "error",
            }[event.kind]
        if "prefer" in text or "style" in text:
            return "preference"
        if "must" in text or "avoid" in text or "require" in text:
            return "instruction"
        if "bug" in text or "failed" in text or "gotcha" in text:
            return "error"
        if "decide" in text or "because" in text:
            return "decision"
        return "observation"

    def _is_memory_worthy(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in DECISION_MARKERS)

    def _query_for(
        self, skill_name: str, prompt: str, cwd: str, files: list[str]
    ) -> str:
        return " ".join([self.project_slug, skill_name, prompt, cwd, *files])

    def _title_from(self, event: SkillEvent) -> str:
        title = re.sub(r"\s+", " ", event.text).strip()
        return title[:76] + "..." if len(title) > 79 else title

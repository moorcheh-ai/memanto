"""Reusable bridge between skill lifecycle events and Memanto memory."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


SECRET_RE = re.compile(
    r"(api[\s_-]?key|secret|token|password|private[\s_-]?key|bearer\s+[a-z0-9._-]+)",
    re.IGNORECASE,
)
INJECTION_RE = re.compile(
    r"(ignore (all )?(previous|prior) instructions|system prompt|developer message|"
    r"hidden instruction|if (an )?(ai|llm|assistant|intelligent system) is reading|"
    r"reveal.*(prompt|secret|credential|private|system))",
    re.IGNORECASE,
)
SIGNAL_RE = re.compile(
    r"\b(decision|preference|prefer|always|never|avoid|constraint|rule|"
    r"architecture|use|do not|don't|must|keep|style|pattern|convention)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)


@dataclass(slots=True)
class SkillEvent:
    """Normalized event from a skill runner or Claude Code hook."""

    skill: str
    project: str
    file_path: str = ""
    input: str = ""
    output: str = ""
    cwd: str = ""
    status: str = "completed"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SkillEvent":
        """Create an event from common hook and wrapper payload shapes."""
        cwd = str(payload.get("cwd") or payload.get("workspace") or "")
        file_path = str(
            payload.get("file_path")
            or payload.get("path")
            or payload.get("active_file")
            or ""
        )
        project = str(
            payload.get("project")
            or payload.get("repo")
            or Path(cwd).name
            or "default-project"
        )
        skill = str(
            payload.get("skill")
            or payload.get("command")
            or payload.get("hook_event_name")
            or "unknown-skill"
        )
        return cls(
            skill=skill,
            project=project,
            file_path=file_path,
            input=str(payload.get("input") or payload.get("prompt") or ""),
            output=str(payload.get("output") or payload.get("transcript") or ""),
            cwd=cwd,
            status=str(payload.get("status") or "completed"),
        )


@dataclass(slots=True)
class MemoryRecord:
    """Small memory shape shared by local and live backends."""

    title: str
    content: str
    project: str
    skill: str
    file_path: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


class MemoryBackend(Protocol):
    """Minimal backend interface used by the bridge."""

    def remember(self, records: list[MemoryRecord]) -> int:
        """Store records and return the number accepted."""

    def recall(self, event: SkillEvent, limit: int, max_chars: int) -> list[MemoryRecord]:
        """Return relevant records for an incoming event."""


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(value) if len(token) > 2}


def _clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line.strip(" -:\t"))
    line = re.sub(r"^(decision|preference|constraint|rule)\s*:\s*", "", line, flags=re.I)
    return line.strip()


def _safe_context_line(value: str) -> str:
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(
        r"</\s*memanto_memory_context\s*>",
        r"<\/memanto_memory_context>",
        value,
        flags=re.IGNORECASE,
    )


class LocalMemoryStore:
    """Deterministic JSON memory store for demos and tests."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def remember(self, records: list[MemoryRecord]) -> int:
        if not records:
            return 0
        existing = self._load()
        seen = {(item["project"], item["content"].lower()) for item in existing}
        accepted = 0
        for record in records:
            key = (record.project, record.content.lower())
            if key in seen:
                continue
            existing.append(asdict(record))
            seen.add(key)
            accepted += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return accepted

    def recall(self, event: SkillEvent, limit: int, max_chars: int) -> list[MemoryRecord]:
        query = " ".join([event.skill, event.file_path, event.input])
        query_tokens = _tokens(query)
        scored: list[tuple[int, MemoryRecord]] = []
        for item in self._load():
            record = MemoryRecord(**item)
            if record.project != event.project:
                continue
            record_tokens = _tokens(" ".join([record.content, record.file_path, *record.tags]))
            score = len(query_tokens & record_tokens)
            if event.file_path and record.file_path:
                shared_parts = set(Path(event.file_path).parts) & set(
                    Path(record.file_path).parts
                )
                score += len(shared_parts) * 2
            if record.skill == event.skill:
                score += 2
            if score > 0:
                scored.append((score, record))

        selected: list[MemoryRecord] = []
        used = 0
        for _, record in sorted(scored, key=lambda pair: pair[0], reverse=True):
            next_size = len(record.content) + 4
            if used + next_size > max_chars:
                if selected:
                    break
                continue
            selected.append(record)
            used += next_size
            if len(selected) >= limit:
                break
        return selected

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


class MemantoBackend:
    """Optional live backend using the Memanto package in this repository."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self._ensure_agent()

    def remember(self, records: list[MemoryRecord]) -> int:
        if not records:
            return 0
        memories = [
            {
                "type": "decision",
                "title": record.title[:100],
                "content": record.content,
                "confidence": 0.84,
                "tags": [record.project, record.skill, *record.tags],
            }
            for record in records
        ]
        self.client.batch_remember(self.agent_id, memories)
        return len(records)

    def recall(self, event: SkillEvent, limit: int, max_chars: int) -> list[MemoryRecord]:
        query = " ".join([event.skill, event.file_path, event.input])
        result = self.client.recall(self.agent_id, query=query, limit=limit)
        records: list[MemoryRecord] = []
        used = 0
        for item in result.get("memories", []):
            content = str(item.get("content") or item.get("text") or "")
            if not content:
                continue
            if used + len(content) > max_chars:
                if records:
                    break
                continue
            records.append(
                MemoryRecord(
                    title=str(item.get("title") or "Memanto memory"),
                    content=content,
                    project=event.project,
                    skill=event.skill,
                    file_path=event.file_path,
                    tags=["memanto-live"],
                )
            )
            used += len(content)
        return records

    def _ensure_agent(self) -> None:
        agents = {agent.get("agent_id") for agent in self.client.list_agents()}
        if self.agent_id not in agents:
            self.client.create_agent(
                self.agent_id,
                pattern="tool",
                description="Claude Code skill memory bridge",
            )
        self.client.activate_agent(self.agent_id)


class SkillMemoryBridge:
    """Coordinates extraction, storage, and prompt injection."""

    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def before_skill(self, event: SkillEvent, limit: int = 8, max_chars: int = 1200) -> str:
        records = self.backend.recall(event, limit=limit, max_chars=max_chars)
        if not records:
            return ""
        lines = ["<memanto_memory_context>"]
        lines.extend(f"- {_safe_context_line(record.content)}" for record in records)
        lines.append("</memanto_memory_context>")
        return "\n".join(lines)

    def after_skill(self, event: SkillEvent) -> int:
        records = extract_memories(event)
        return self.backend.remember(records)


def extract_memories(event: SkillEvent) -> list[MemoryRecord]:
    """Extract durable engineering memories from a completed skill event."""
    combined = "\n".join([event.input, event.output])
    records: list[MemoryRecord] = []
    for raw_line in combined.splitlines():
        if SECRET_RE.search(raw_line):
            continue
        if INJECTION_RE.search(raw_line):
            continue
        if not SIGNAL_RE.search(raw_line):
            continue
        content = _clean_line(raw_line)
        if len(content) < 12 or len(content) > 280:
            continue
        tags = _derive_tags(content, event)
        records.append(
            MemoryRecord(
                title=content[:80],
                content=content,
                project=event.project,
                skill=event.skill,
                file_path=event.file_path,
                tags=tags,
            )
        )
    return records


def _derive_tags(content: str, event: SkillEvent) -> list[str]:
    tags = [event.skill.strip("/") or "skill"]
    suffix = Path(event.file_path).suffix.lstrip(".")
    if suffix:
        tags.append(suffix)
    for word in ("fastapi", "react", "typescript", "python", "stripe", "firebase"):
        if word in content.lower():
            tags.append(word)
    return tags


def build_backend_from_env() -> MemoryBackend:
    backend = os.getenv("MEMANTO_SKILLS_BACKEND", "local").lower()
    if backend == "memanto":
        api_key = os.getenv("MOORCHEH_API_KEY", "")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for live Memanto mode")
        agent_id = os.getenv("MEMANTO_SKILLS_AGENT_ID", "claude-skills-memory")
        return MemantoBackend(api_key=api_key, agent_id=agent_id)

    store_path = os.getenv("MEMANTO_SKILLS_STORE", ".memanto-skills-memory.json")
    return LocalMemoryStore(store_path)


def run_wrapped_command(event: SkillEvent, command: list[str]) -> int:
    """Run a command and store a memory summary from its combined output."""
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    event.output = "\n".join(
        part for part in [completed.stdout, completed.stderr] if part.strip()
    )
    SkillMemoryBridge(build_backend_from_env()).after_skill(event)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode

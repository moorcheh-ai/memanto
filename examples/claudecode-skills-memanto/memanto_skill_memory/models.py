from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class SkillEvent:
    """Input/output captured from one skill invocation."""

    skill_name: str
    prompt: str
    transcript: str
    cwd: str
    command: tuple[str, ...] = ()
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = list(self.command)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillEvent:
        return cls(
            skill_name=str(data["skill_name"]),
            prompt=str(data.get("prompt", "")),
            transcript=str(data.get("transcript", "")),
            cwd=str(data.get("cwd", "")),
            command=tuple(str(part) for part in data.get("command", ())),
            started_at=str(data.get("started_at", utc_now_iso())),
            ended_at=str(data.get("ended_at", utc_now_iso())),
            metadata={str(k): str(v) for k, v in data.get("metadata", {}).items()},
        )


@dataclass(frozen=True)
class MemoryCandidate:
    """One durable engineering memory extracted from a skill transcript."""

    memory_type: str
    title: str
    content: str
    confidence: float = 0.8
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryCandidate:
        return cls(
            memory_type=str(data["memory_type"]),
            title=str(data["title"]),
            content=str(data["content"]),
            confidence=float(data.get("confidence", 0.8)),
            tags=[str(tag) for tag in data.get("tags", [])],
        )


@dataclass(frozen=True)
class RecallResult:
    """Memory plus its source event and local relevance score."""

    memory: MemoryCandidate
    event: SkillEvent
    score: float

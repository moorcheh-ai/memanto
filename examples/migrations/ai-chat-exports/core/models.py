from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "user_preference"
    CONTEXT = "context"
    EVENT = "event"
    DECISION = "decision"
    LEARNING = "learning"
    OBSERVATION = "observation"
    INSTRUCTION = "instruction"
    RELATIONSHIP = "relationship"
    COMMITMENT = "commitment"
    GOAL = "goal"
    ARTIFACT = "artifact"
    ERROR = "error"


@dataclass
class MemoryEntity:
    source_type: MemoryType
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    confidence: float = 0.8
    provenance: str = "explicit_statement"
    source: str = ""
    source_ref: str = ""
    metadata: dict = field(default_factory=dict)

    def to_okf_frontmatter(self) -> str:
        ts = ""
        if self.timestamp:
            ts = self.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        tags_str = ", ".join(self.tags) if self.tags else ""

        lines = [
            "---",
            f"type: {self.source_type.value}",
            f'title: "{self._escape_yaml(self.title)}"',
            f'description: "{self._escape_yaml(self.content[:120])}"',
            f"tags: [{tags_str}]",
        ]
        if ts:
            lines.append(f"timestamp: {ts}")
        if self.source_ref:
            lines.append(f"resource: {self.source_ref}")
        lines.append("x_memanto:")
        lines.append(f"  confidence: {self.confidence}")
        lines.append(f"  provenance: {self.provenance}")
        lines.append(f"  source: {self.source}")
        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    def _escape_yaml(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

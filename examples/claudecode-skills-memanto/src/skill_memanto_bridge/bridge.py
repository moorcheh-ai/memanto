from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import LocalJsonlBackend, MemoryBackend, build_backend, default_store_path


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
]


@dataclass(frozen=True)
class BridgeConfig:
    store_path: Path = default_store_path()
    max_injected: int = 5
    max_extracted: int = 8

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        return cls(
            store_path=default_store_path(),
            max_injected=int(os.environ.get("SKILL_MEMANTO_MAX_INJECTED", "5")),
            max_extracted=int(os.environ.get("SKILL_MEMANTO_MAX_EXTRACTED", "8")),
        )


class MemoryBridge:
    def __init__(
        self,
        *,
        config: BridgeConfig | None = None,
        backend: MemoryBackend | None = None,
    ) -> None:
        self.config = config or BridgeConfig.from_env()
        self.backend = backend or self._backend_from_config()

    def _backend_from_config(self) -> MemoryBackend:
        requested = os.environ.get("SKILL_MEMANTO_BACKEND", "local").strip().lower()
        if requested in {"live", "memanto", "sdk"}:
            return build_backend()
        return LocalJsonlBackend(self.config.store_path)

    def pre_run(self, *, skill: str, task: str, path: str) -> str:
        query = f"skill={skill} task={task} path={path}"
        memories = self.backend.recall(query, limit=self.config.max_injected)
        if not memories:
            return ""

        lines = [
            "<!-- memanto-skill-memory:start -->",
            "### Memanto memory context",
            "Apply these previous engineering decisions if they are relevant:",
        ]
        for memory in memories:
            memory_type = memory.get("memory_type", "context")
            title = clean_inline(str(memory.get("title", "Memory")))
            content = clean_inline(str(memory.get("content", "")))
            lines.append(f"- [{memory_type}] {title}: {content}")
        lines.append("<!-- memanto-skill-memory:end -->")
        return "\n".join(lines)

    def post_run(
        self,
        *,
        skill: str,
        task: str,
        transcript: str,
        path: str,
    ) -> list[dict[str, Any]]:
        extracted = extract_active_memories(
            transcript,
            max_items=self.config.max_extracted,
        )
        saved: list[dict[str, Any]] = []
        for item in extracted:
            saved.append(
                self.backend.remember(
                    title=item["title"],
                    content=item["content"],
                    memory_type=item["memory_type"],
                    tags=sorted(set(["developer-skills", skill, *item["tags"]])),
                    source=f"skill:{skill}",
                    metadata={"skill": skill, "task": task, "path": path},
                    confidence=item["confidence"],
                )
            )
        return saved


def extract_active_memories(transcript: str, *, max_items: int) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in transcript.splitlines():
        line = normalise_line(raw_line)
        if not is_memorable(line):
            continue
        redacted = redact(line)
        key = redacted.lower()
        if key in seen:
            continue
        seen.add(key)
        memory_type = classify(redacted)
        memories.append(
            {
                "title": title_for(redacted),
                "content": redacted,
                "memory_type": memory_type,
                "tags": tags_for(redacted, memory_type),
                "confidence": 0.86,
            }
        )
        if len(memories) >= max_items:
            break
    return memories


def normalise_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.)]\s+", "", line)
    return re.sub(r"\s+", " ", line)


def is_memorable(line: str) -> bool:
    if len(line) < 18 or len(line) > 500:
        return False
    lowered = line.lower()
    signals = [
        "we decided",
        "decided to",
        "decision:",
        "prefer",
        "preference:",
        "avoid ",
        "do not ",
        "never ",
        "must ",
        "keep ",
        "use ",
        "always ",
    ]
    return any(signal in lowered for signal in signals)


def classify(line: str) -> str:
    lowered = line.lower()
    if "prefer" in lowered or "preference:" in lowered:
        return "preference"
    if "decided" in lowered or "decision:" in lowered:
        return "decision"
    if any(signal in lowered for signal in ["avoid ", "do not ", "never ", "must "]):
        return "instruction"
    return "learning"


def tags_for(line: str, memory_type: str) -> list[str]:
    tags = [memory_type]
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", line):
        lowered = token.lower()
        if lowered in {
            "decided",
            "preference",
            "should",
            "without",
            "before",
            "after",
            "using",
        }:
            continue
        tags.append(lowered)
        if len(tags) >= 5:
            break
    return tags


def title_for(line: str) -> str:
    clean = re.sub(r"(?i)^(we\s+)?(decided to|decision:|preference:)\s*", "", line)
    clean = clean.rstrip(".")
    return clean[:80] or "Developer skill memory"


def redact(line: str) -> str:
    redacted = line
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=<redacted>" if match.groups() else "<redacted>", redacted)
    return redacted


def clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", redact(value)).strip()

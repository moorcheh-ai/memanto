#!/usr/bin/env python3
"""Memanto lifecycle hooks for mattpocock/skills-style commands."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

VALID_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


@dataclass
class SkillMemory:
    """A portable memory shape that maps cleanly to Memanto's typed schema."""

    type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    source_skill: str
    paths: list[str]
    created_at: str


class MemoryBackend(Protocol):
    def remember(self, memory: SkillMemory) -> str:
        """Persist one extracted memory and return its id."""

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]:
        """Return memories relevant to a new skill invocation."""

    def answer(self, question: str, limit: int = 5) -> str | None:
        """Return grounded guidance from remembered context when available."""


class LocalJsonBackend:
    """Credential-free backend for tests, demos, and reviewer validation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: SkillMemory) -> str:
        existing = self._read()
        memory_id = f"local-{len(existing) + 1:04d}"
        payload = asdict(memory) | {"id": memory_id}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return memory_id

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]:
        query_terms = _terms(query)
        scored: list[tuple[int, SkillMemory]] = []
        for payload in self._read():
            memory = SkillMemory(
                type=payload["type"],
                title=payload["title"],
                content=payload["content"],
                confidence=float(payload["confidence"]),
                tags=list(payload["tags"]),
                source_skill=payload["source_skill"],
                paths=list(payload["paths"]),
                created_at=payload["created_at"],
            )
            haystack = " ".join(
                [memory.title, memory.content, memory.source_skill, *memory.tags, *memory.paths]
            )
            score = len(query_terms & _terms(haystack))
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def answer(self, question: str, limit: int = 5) -> str | None:
        memories = self.recall(question, limit=limit)
        if not memories:
            return None
        return "Apply remembered context: " + " ".join(memory.content for memory in memories[:2])

    def _read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


class MemantoSdkBackend:
    """Live backend using Memanto's SdkClient when credentials are available."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.app.utils.errors import AgentNotFoundError
        from memanto.cli.client.sdk_client import SdkClient

        self.client = SdkClient(api_key)
        self.agent_id = agent_id

        try:
            self.client.get_agent(agent_id)
        except AgentNotFoundError:
            self.client.create_agent(
                agent_id,
                pattern="tool",
                description="Shared memory for Claude Code skill executions",
            )
        self.client.activate_agent(agent_id)

    def remember(self, memory: SkillMemory) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.type,
            title=memory.title[:100],
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source_skill,
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]:
        result = self.client.recall(self.agent_id, query=query, limit=limit)
        memories = []
        for item in result.get("memories", []):
            memories.append(
                SkillMemory(
                    type=str(item.get("type", "context")),
                    title=str(item.get("title", "Untitled memory")),
                    content=str(item.get("content", "")),
                    confidence=float(item.get("confidence", 0.8)),
                    tags=list(item.get("tags", [])),
                    source_skill=str(item.get("source", "memanto")),
                    paths=[],
                    created_at=str(item.get("created_at", "")),
                )
            )
        return memories

    def answer(self, question: str, limit: int = 5) -> str | None:
        result = self.client.answer(
            self.agent_id,
            question=question,
            limit=limit,
            header_prompt=(
                "Answer as a concise engineering constraint for the next Claude Code "
                "skill invocation. Use only remembered facts."
            ),
        )
        answer = str(result.get("answer", "")).strip()
        return answer or None


def backend_from_args(args: argparse.Namespace) -> MemoryBackend:
    if args.backend == "memanto":
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise SystemExit("MOORCHEH_API_KEY is required for --backend memanto")
        return MemantoSdkBackend(api_key, args.agent_id)
    return LocalJsonBackend(Path(args.store))


def before_skill(
    backend: MemoryBackend,
    skill: str,
    prompt: str,
    paths: list[str],
    limit: int = 5,
    include_answer: bool = True,
) -> str:
    query = " ".join([skill, prompt, *paths])
    memories = backend.recall(query, limit=limit)
    if not memories:
        return "MEMANTO_SKILL_CONTEXT:\n- No relevant prior engineering memories found."

    lines = ["MEMANTO_SKILL_CONTEXT:"]
    answer = backend.answer(query, limit=limit) if include_answer else None
    if answer:
        lines.append(f"- [memanto-answer] {answer}")
    for memory in memories:
        tags = ", ".join(memory.tags) if memory.tags else "untagged"
        lines.append(f"- [{memory.type}] {memory.title} ({tags})")
        lines.append(f"  {memory.content}")
    return "\n".join(lines)


def after_skill(
    backend: MemoryBackend,
    skill: str,
    prompt: str,
    transcript: str,
    paths: list[str],
) -> list[tuple[str, SkillMemory]]:
    memories = extract_memories(skill, prompt, transcript, paths)
    return [(backend.remember(memory), memory) for memory in memories]


def extract_memories(
    skill: str,
    prompt: str,
    transcript: str,
    paths: list[str],
) -> list[SkillMemory]:
    """Extract durable engineering memories from a finished skill transcript."""

    lines = [line.strip(" -\t") for line in transcript.splitlines() if line.strip()]
    memories: list[SkillMemory] = []
    seen: set[str] = set()

    patterns = [
        (
            "decision",
            0.9,
            r"(?i)^(?:decision|decided|architecture decision)[:\-]\s*(.+)$",
            "Decision from skill run",
        ),
        (
            "preference",
            0.8,
            r"(?i)^(?:preference|style rule|convention)[:\-]\s*(.+)$",
            "Developer preference from skill run",
        ),
        (
            "instruction",
            0.85,
            r"(?i)^(?:rule|constraint|must|do not)[:\-]\s*(.+)$",
            "Instruction from skill run",
        ),
        (
            "artifact",
            0.75,
            r"(?i)^(?:artifact|changed file|output)[:\-]\s*(.+)$",
            "Artifact from skill run",
        ),
    ]

    for line in lines:
        for memory_type, confidence, pattern, fallback_title in patterns:
            match = re.match(pattern, line)
            if not match:
                continue
            content = match.group(1).strip()
            if not content or content in seen:
                continue
            seen.add(content)
            memories.append(
                SkillMemory(
                    type=memory_type,
                    title=_title(content, fallback_title),
                    content=content,
                    confidence=confidence,
                    tags=_tags(skill, prompt, paths),
                    source_skill=skill,
                    paths=paths,
                    created_at=_now(),
                )
            )

    if not memories:
        summary = " ".join(lines[:3])[:500]
        if summary:
            memories.append(
                SkillMemory(
                    type="context",
                    title=f"Summary from {skill}",
                    content=summary,
                    confidence=0.55,
                    tags=_tags(skill, prompt, paths),
                    source_skill=skill,
                    paths=paths,
                    created_at=_now(),
                )
            )

    return memories


def _tags(skill: str, prompt: str, paths: list[str]) -> list[str]:
    raw = [skill.strip("/").replace("_", "-")]
    for path in paths:
        parsed = Path(path)
        if parsed.parts:
            raw.append(parsed.parts[0])
        if parsed.stem:
            raw.append(parsed.stem)
    raw.extend(term for term in sorted(_terms(prompt)) if len(term) > 5)
    tags = []
    for tag in raw:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", tag.lower()).strip("-")
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags[:8]


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[a-zA-Z0-9_/-]{3,}", text)}


def _title(content: str, fallback: str) -> str:
    title = re.sub(r"\s+", " ", content).strip()
    return title[:96] + "..." if len(title) > 99 else title or fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text_arg(value: str) -> str:
    path = Path(value)
    return path.read_text(encoding="utf-8") if path.exists() else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument("--store", default=".memanto-local/skill-memory.jsonl")
    parser.add_argument("--agent-id", default="claudecode-skills-demo")

    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before")
    before.add_argument("--skill", required=True)
    before.add_argument("--prompt", required=True)
    before.add_argument("--path", action="append", default=[])
    before.add_argument("--no-answer", action="store_true")

    after = subparsers.add_parser("after")
    after.add_argument("--skill", required=True)
    after.add_argument("--prompt", required=True)
    after.add_argument("--transcript", required=True)
    after.add_argument("--path", action="append", default=[])

    return parser


def main() -> int:
    args = build_parser().parse_args()
    backend = backend_from_args(args)

    if args.command == "before":
        print(
            before_skill(
                backend,
                args.skill,
                args.prompt,
                args.path,
                include_answer=not args.no_answer,
            )
        )
        return 0

    transcript = _read_text_arg(args.transcript)
    stored = after_skill(backend, args.skill, args.prompt, transcript, args.path)
    print(json.dumps({"stored": len(stored), "memory_ids": [item[0] for item in stored]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from memanto_skill_memory.models import MemoryCandidate, RecallResult, SkillEvent


class MemoryBackend(Protocol):
    def remember(
        self, memories: list[MemoryCandidate], event: SkillEvent
    ) -> list[MemoryCandidate]: ...

    def recall(self, query: str, limit: int = 5) -> list[RecallResult]: ...


class LocalJsonlBackend:
    """Credential-free backend for demos, tests, and PR review."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def remember(
        self, memories: list[MemoryCandidate], event: SkillEvent
    ) -> list[MemoryCandidate]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stored: list[MemoryCandidate] = []
        with self.path.open("a", encoding="utf-8") as stream:
            for memory in memories:
                tagged = _with_event_tags(memory, event)
                stream.write(
                    json.dumps(
                        {"memory": tagged.to_dict(), "event": event.to_dict()},
                        sort_keys=True,
                    )
                    + "\n"
                )
                stored.append(tagged)
        return stored

    def recall(self, query: str, limit: int = 5) -> list[RecallResult]:
        if not self.path.exists():
            return []

        query_terms = _tokenize(query)
        matches: list[RecallResult] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            memory = MemoryCandidate.from_dict(raw["memory"])
            event = SkillEvent.from_dict(raw["event"])
            score = _score(query_terms, memory, event)
            if score > 0:
                matches.append(RecallResult(memory=memory, event=event, score=score))

        matches.sort(key=lambda result: result.score, reverse=True)
        return matches[:limit]


class MemantoSdkBackend:
    """Live backend that stores and recalls memories with the Memanto SDK."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self._ensure_active_agent()

    def remember(
        self, memories: list[MemoryCandidate], event: SkillEvent
    ) -> list[MemoryCandidate]:
        stored: list[MemoryCandidate] = []
        for memory in memories:
            tagged = _with_event_tags(memory, event)
            self.client.remember(
                agent_id=self.agent_id,
                memory_type=tagged.memory_type,
                title=tagged.title,
                content=tagged.content,
                confidence=tagged.confidence,
                tags=tagged.tags,
                source=f"skill:{event.skill_name}",
                provenance="inferred",
            )
            stored.append(tagged)
        return stored

    def recall(self, query: str, limit: int = 5) -> list[RecallResult]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        recalled: list[RecallResult] = []
        for item in result.get("memories", []):
            memory = MemoryCandidate(
                memory_type=str(item.get("type") or "context"),
                title=str(item.get("title") or "Memory"),
                content=str(item.get("content") or ""),
                confidence=float(item.get("confidence") or 0.8),
                tags=[str(tag) for tag in item.get("tags") or []],
            )
            recalled.append(
                RecallResult(
                    memory=memory,
                    event=SkillEvent(
                        skill_name=_source_skill(memory.tags),
                        prompt=query,
                        transcript="",
                        cwd=os.getcwd(),
                    ),
                    score=float(item.get("similarity_score") or 1.0),
                )
            )
        return recalled

    def _ensure_active_agent(self) -> None:
        try:
            self.client.get_agent(self.agent_id)
        except Exception:
            self.client.create_agent(
                self.agent_id,
                pattern="tool",
                description="Memanto memory companion for developer skills.",
            )
        self.client.activate_agent(self.agent_id)


def backend_from_env(cwd: Path | None = None) -> MemoryBackend:
    backend = os.environ.get("MEMANTO_SKILL_BACKEND", "local").strip().lower()
    if backend == "memanto":
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        agent_id = os.environ.get("MEMANTO_AGENT_ID", "developer-skills")
        if not api_key:
            raise RuntimeError(
                "MEMANTO_SKILL_BACKEND=memanto requires MOORCHEH_API_KEY"
            )
        return MemantoSdkBackend(api_key=api_key, agent_id=agent_id)

    root = cwd or Path.cwd()
    path = Path(
        os.environ.get(
            "MEMANTO_SKILL_LOCAL_STORE",
            str(root / ".memanto-skills" / "memories.jsonl"),
        )
    )
    return LocalJsonlBackend(path)


def _with_event_tags(memory: MemoryCandidate, event: SkillEvent) -> MemoryCandidate:
    tags = list(dict.fromkeys([*memory.tags, event.skill_name, f"project:{event.cwd}"]))
    return replace(memory, tags=tags)


def _source_skill(tags: list[str]) -> str:
    for tag in tags:
        if not tag.startswith("project:"):
            return tag
    return "memanto"


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_/-]+", text.casefold())
        if len(token) > 2
    }


def _score(query_terms: set[str], memory: MemoryCandidate, event: SkillEvent) -> float:
    haystack = " ".join(
        [memory.title, memory.content, " ".join(memory.tags), event.skill_name]
    )
    terms = _tokenize(haystack)
    overlap = query_terms & terms
    if not overlap:
        return 0.0
    return len(overlap) + memory.confidence

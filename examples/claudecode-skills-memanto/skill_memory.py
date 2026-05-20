"""Lifecycle memory hooks for developer skill executions.

The module has two backends:

* LocalJsonlBackend: credential-free review and tests.
* MemantoSdkBackend: optional live Memanto storage through SdkClient.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}

DEFAULT_LOCAL_STORE = Path(".memanto-skill-memory.jsonl")
DEFAULT_AGENT_ID = "developer-skills"


@dataclass(frozen=True)
class EngineeringMemory:
    """A typed engineering memory extracted from a skill run."""

    memory_type: str
    title: str
    content: str
    confidence: float = 0.8
    tags: list[str] = field(default_factory=list)
    source: str = "skill-memory-hook"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MemoryBackend(Protocol):
    """Storage interface shared by local and live Memanto backends."""

    def remember(self, memory: EngineeringMemory) -> str:
        """Store a memory and return its identifier."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        tags: list[str] | None = None,
    ) -> list[EngineeringMemory]:
        """Return memories relevant to the query."""


class LocalJsonlBackend:
    """Small deterministic backend for local demos and pull request review."""

    def __init__(self, path: Path = DEFAULT_LOCAL_STORE) -> None:
        self.path = path

    def remember(self, memory: EngineeringMemory) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        memory_id = str(uuid4())
        payload = {"id": memory_id, **asdict(memory)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return memory_id

    def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        tags: list[str] | None = None,
    ) -> list[EngineeringMemory]:
        if not self.path.exists():
            return []

        query_tokens = _tokens(query)
        requested_tags = set(tags or [])
        scored: list[tuple[float, EngineeringMemory]] = []

        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                memory = EngineeringMemory(
                    memory_type=raw["memory_type"],
                    title=raw["title"],
                    content=raw["content"],
                    confidence=float(raw.get("confidence", 0.8)),
                    tags=list(raw.get("tags", [])),
                    source=raw.get("source", "skill-memory-hook"),
                    created_at=raw.get("created_at", ""),
                )
                tag_overlap = requested_tags.intersection(memory.tags)
                text = f"{memory.title} {memory.content} {' '.join(memory.tags)}"
                token_overlap = query_tokens.intersection(_tokens(text))
                score = len(token_overlap) + (2 * len(tag_overlap))
                if score > 0 or not query_tokens:
                    scored.append((score + memory.confidence, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]


class MemantoSdkBackend:
    """Live backend using Memanto's SDK client.

    Importing SdkClient lazily keeps local validation free of optional network
    setup and private credentials.
    """

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT_ID) -> None:
        if not api_key.strip():
            raise ValueError("api_key must be provided for sdk backend")

        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id,
                pattern="tool",
                description="Shared memory for developer skill executions",
            )
        except AgentAlreadyExistsError:
            pass
        self.client.activate_agent(agent_id)

    def remember(self, memory: EngineeringMemory) -> str:
        result = self.client.remember(
            self.agent_id,
            memory.memory_type,
            memory.title,
            memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
            provenance="observed",
        )
        return str(result["memory_id"])

    def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        tags: list[str] | None = None,
    ) -> list[EngineeringMemory]:
        result = self.client.recall(
            self.agent_id,
            query,
            limit=limit,
            tags=tags,
            min_confidence=0.45,
        )
        memories: list[EngineeringMemory] = []
        for raw in result.get("memories", []):
            memories.append(_memory_from_sdk_result(raw))
        return memories


@dataclass(frozen=True)
class SkillRun:
    """Metadata describing one developer skill execution."""

    skill: str
    task: str
    workspace: str = "default"
    files: tuple[str, ...] = ()

    @property
    def tags(self) -> list[str]:
        file_tags = [f"path:{Path(file_name).parent}" for file_name in self.files]
        return [f"skill:{self.skill}", f"workspace:{self.workspace}", *file_tags]

    @property
    def query(self) -> str:
        return " ".join([self.skill, self.task, self.workspace, *self.files])


class SkillMemoryHook:
    """Coordinates extraction after a run and context injection before a run."""

    def __init__(self, backend: MemoryBackend) -> None:
        self.backend = backend

    def before_skill(self, run: SkillRun, limit: int = 6) -> str:
        memories = self.backend.recall(
            run.query,
            limit=limit,
            tags=[f"workspace:{run.workspace}"],
        )
        return render_injection_block(run, memories)

    def after_skill(self, run: SkillRun, transcript: str) -> list[EngineeringMemory]:
        memories = distill_memories(transcript, run)
        for memory in memories:
            self.backend.remember(memory)
        return memories


def distill_memories(transcript: str, run: SkillRun) -> list[EngineeringMemory]:
    """Extract high-signal engineering memories from a skill transcript."""

    memories: list[EngineeringMemory] = []
    seen: set[str] = set()

    for raw_line in transcript.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue

        memory_type = _classify_line(line)
        if not memory_type:
            continue

        content = _strip_label(line)
        key = re.sub(r"\W+", " ", f"{memory_type} {content}").lower().strip()
        if key in seen:
            continue
        seen.add(key)

        confidence = _confidence_for(memory_type, line)
        memories.append(
            EngineeringMemory(
                memory_type=memory_type,
                title=_title_for(content),
                content=content,
                confidence=confidence,
                tags=[*run.tags, f"type:{memory_type}"],
            )
        )

    if not memories and transcript.strip():
        summary = " ".join(transcript.strip().split())[:400]
        memories.append(
            EngineeringMemory(
                memory_type="observation",
                title=f"{run.skill} run summary",
                content=summary,
                confidence=0.45,
                tags=[*run.tags, "type:observation"],
            )
        )

    return memories


def render_injection_block(run: SkillRun, memories: list[EngineeringMemory]) -> str:
    """Render a compact prompt block for a later skill invocation."""

    if not memories:
        return (
            "## Memanto Skill Memory\n"
            f"No relevant memories found for `{run.skill}` in workspace "
            f"`{run.workspace}`.\n"
        )

    lines = [
        "## Memanto Skill Memory",
        f"Relevant prior engineering context for `{run.skill}`:",
    ]
    for index, memory in enumerate(memories, start=1):
        lines.append(
            f"{index}. [{memory.memory_type}] {memory.title}: {memory.content}"
        )
    lines.append("")
    lines.append(
        "Use these memories as constraints when they fit the current task; "
        "ignore any that conflict with newer user instructions."
    )
    return "\n".join(lines)


def build_backend_from_env() -> MemoryBackend:
    backend_name = os.environ.get("MEMANTO_MEMORY_BACKEND", "local").lower()
    if backend_name == "sdk":
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        agent_id = os.environ.get("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID)
        return MemantoSdkBackend(api_key=api_key, agent_id=agent_id)

    store_path = Path(os.environ.get("MEMANTO_LOCAL_STORE", str(DEFAULT_LOCAL_STORE)))
    return LocalJsonlBackend(store_path)


def _classify_line(line: str) -> str | None:
    lowered = line.lower()
    prefix = lowered.split(":", 1)[0]
    prefix_map = {
        "decision": "decision",
        "preference": "preference",
        "constraint": "instruction",
        "instruction": "instruction",
        "artifact": "artifact",
        "goal": "goal",
        "learning": "learning",
        "error": "error",
        "context": "context",
    }
    if prefix in prefix_map:
        return prefix_map[prefix]

    patterns = [
        (r"\b(decided|choose|selected|accepted)\b", "decision"),
        (r"\b(prefer|preference|convention|style)\b", "preference"),
        (r"\b(must|should|avoid|do not|never|always)\b", "instruction"),
        (r"\b(adr|artifact|contract|schema|interface)\b", "artifact"),
        (r"\b(goal|objective|target)\b", "goal"),
        (r"\b(regression|failure|bug|error)\b", "error"),
    ]
    for pattern, memory_type in patterns:
        if re.search(pattern, lowered):
            return memory_type
    return None


def _strip_label(line: str) -> str:
    if ":" in line:
        label, rest = line.split(":", 1)
        if len(label.split()) <= 4:
            return rest.strip()
    return line


def _title_for(content: str) -> str:
    words = content.strip().split()
    title = " ".join(words[:10])
    if len(words) > 10:
        title += "..."
    return title[:100]


def _confidence_for(memory_type: str, line: str) -> float:
    if ":" in line and _classify_line(line):
        return 0.9
    if memory_type in {"decision", "instruction"}:
        return 0.82
    if memory_type in {"preference", "artifact"}:
        return 0.75
    return 0.65


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
        if token
        not in {
            "and",
            "for",
            "the",
            "this",
            "that",
            "with",
            "from",
            "into",
            "skill",
        }
    }


def _memory_from_sdk_result(raw: dict[str, Any]) -> EngineeringMemory:
    memory_type = raw.get("type") or raw.get("memory_type") or "context"
    if memory_type not in VALID_MEMORY_TYPES:
        memory_type = "context"

    content = raw.get("content") or raw.get("text") or json.dumps(raw, sort_keys=True)
    title = raw.get("title") or _title_for(str(content))
    return EngineeringMemory(
        memory_type=str(memory_type),
        title=str(title),
        content=str(content),
        confidence=float(raw.get("confidence", 0.7)),
        tags=list(raw.get("tags", [])),
        source=str(raw.get("source", "memanto-sdk")),
        created_at=str(raw.get("created_at", "")),
    )


def _read_transcript(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def _build_run(args: argparse.Namespace) -> SkillRun:
    return SkillRun(
        skill=args.skill,
        task=args.task,
        workspace=args.workspace,
        files=tuple(args.file or ()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="render memory context")
    before.add_argument("--skill", required=True)
    before.add_argument("--task", required=True)
    before.add_argument("--workspace", default="default")
    before.add_argument("--file", action="append")
    before.add_argument("--limit", type=int, default=6)

    after = subparsers.add_parser("after", help="store memories from a transcript")
    after.add_argument("--skill", required=True)
    after.add_argument("--task", required=True)
    after.add_argument("--workspace", default="default")
    after.add_argument("--file", action="append")
    after.add_argument("--transcript")

    args = parser.parse_args(argv)
    hook = SkillMemoryHook(build_backend_from_env())
    run = _build_run(args)

    if args.command == "before":
        print(hook.before_skill(run, limit=args.limit))
        return 0

    transcript = _read_transcript(args.transcript)
    memories = hook.after_skill(run, transcript)
    print(json.dumps({"stored": len(memories), "memories": [asdict(m) for m in memories]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

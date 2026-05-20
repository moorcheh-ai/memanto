"""Cross-skill Memanto memory hooks for Claude Code-style skills.

The module exposes a tiny lifecycle:

1. ``pre_skill`` recalls relevant memories for the current task.
2. A skill command runs with that context.
3. ``post_skill`` distills the transcript into durable engineering memories.

Local JSONL storage is used by default so reviewers can validate the example
without credentials. The SDK backend can be selected when MOORCHEH_API_KEY is
available.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol


DEFAULT_STORE = Path(".memanto-skill-memory.jsonl")
DEFAULT_AGENT_ID = "claude-code-skills"
SIGNALS = {
    "decision": re.compile(r"\b(decision|decided|choose|keep|standardize)\b", re.I),
    "preference": re.compile(r"\b(prefer|preference|style|convention)\b", re.I),
    "instruction": re.compile(r"\b(must|always|never|require|constraint)\b", re.I),
    "artifact": re.compile(r"\b(file|module|component|endpoint|api|schema)\b", re.I),
}


@dataclass(frozen=True)
class EngineeringMemory:
    content: str
    memory_type: str = "decision"
    source_skill: str = "unknown"
    confidence: float = 0.75
    tags: tuple[str, ...] = ()


class MemoryBackend(Protocol):
    def remember(self, memory: EngineeringMemory) -> None:
        """Persist a memory."""

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        """Return relevant memories."""


class LocalJsonlBackend:
    def __init__(self, path: Path = DEFAULT_STORE) -> None:
        self.path = path

    def remember(self, memory: EngineeringMemory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(memory), sort_keys=True) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        if not self.path.exists():
            return []

        query_terms = tokenize(query)
        scored: list[tuple[int, EngineeringMemory]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                data = json.loads(line)
                memory = EngineeringMemory(
                    content=data["content"],
                    memory_type=data.get("memory_type", "decision"),
                    source_skill=data.get("source_skill", "unknown"),
                    confidence=float(data.get("confidence", 0.75)),
                    tags=tuple(data.get("tags", ())),
                )
                memory_terms = tokenize(memory.content + " " + " ".join(memory.tags))
                score = len(query_terms & memory_terms)
                if score:
                    scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].confidence), reverse=True)
        return [memory for _, memory in scored[:limit]]


class SdkBackend:
    def __init__(self, agent_id: str = DEFAULT_AGENT_ID) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=os.environ.get("MOORCHEH_API_KEY"))

    def remember(self, memory: EngineeringMemory) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            content=memory.content,
            memory_type=memory.memory_type,
            tags=",".join(memory.tags),
            confidence=memory.confidence,
            source=memory.source_skill,
        )

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        memories = result.get("memories", result if isinstance(result, list) else [])
        output: list[EngineeringMemory] = []
        for item in memories[:limit]:
            content = item.get("content") or item.get("text") or str(item)
            output.append(EngineeringMemory(content=content, source_skill="memanto"))
        return output


def tokenize(text: str) -> set[str]:
    return {part.lower() for part in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)}


def build_backend(kind: str, store: Path, agent_id: str) -> MemoryBackend:
    if kind == "sdk":
        return SdkBackend(agent_id=agent_id)
    return LocalJsonlBackend(store)


def distill_transcript(skill: str, transcript: str) -> list[EngineeringMemory]:
    memories: list[EngineeringMemory] = []
    seen: set[str] = set()
    for raw_line in transcript.splitlines():
        line = raw_line.strip(" -*\t")
        if len(line) < 12 or line in seen:
            continue

        matched_type = None
        for memory_type, pattern in SIGNALS.items():
            if pattern.search(line):
                matched_type = memory_type
                break

        if not matched_type:
            continue

        seen.add(line)
        confidence = 0.9 if matched_type in {"decision", "instruction"} else 0.8
        memories.append(
            EngineeringMemory(
                content=line,
                memory_type=matched_type,
                source_skill=skill,
                confidence=confidence,
                tags=tuple(sorted(tokenize(skill + " " + line)))[:8],
            )
        )

    return memories


def format_injected_context(memories: Iterable[EngineeringMemory]) -> str:
    lines = [memory.content for memory in memories]
    if not lines:
        return "No prior engineering memories found."
    return "Relevant engineering memories:\n" + "\n".join(f"- {line}" for line in lines)


def pre_skill(backend: MemoryBackend, skill: str, task: str, limit: int = 5) -> str:
    return format_injected_context(backend.recall(f"{skill} {task}", limit=limit))


def post_skill(backend: MemoryBackend, skill: str, transcript: str) -> int:
    memories = distill_transcript(skill, transcript)
    for memory in memories:
        backend.remember(memory)
    return len(memories)


def repeated_instruction_reduction(previous: str, current: str, injected: str) -> dict[str, int]:
    previous_terms = tokenize(previous)
    current_terms = tokenize(current)
    injected_terms = tokenize(injected)
    repeated = previous_terms & current_terms
    covered = repeated & injected_terms
    return {
        "repeated_terms": len(repeated),
        "covered_by_memory": len(covered),
        "remaining_repetition": len(repeated - covered),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["pre", "post", "distill"])
    parser.add_argument("--backend", choices=["local", "sdk"], default="local")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--transcript-file", type=Path)
    args = parser.parse_args(argv)

    backend = build_backend(args.backend, args.store, args.agent_id)

    if args.phase == "pre":
        print(pre_skill(backend, args.skill, args.task))
        return 0

    transcript = (
        args.transcript_file.read_text(encoding="utf-8")
        if args.transcript_file
        else sys.stdin.read()
    )

    if args.phase == "distill":
        for memory in distill_transcript(args.skill, transcript):
            print(json.dumps(asdict(memory), sort_keys=True))
        return 0

    count = post_skill(backend, args.skill, transcript)
    print(f"stored {count} memories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


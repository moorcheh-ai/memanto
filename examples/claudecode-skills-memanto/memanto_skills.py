from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

load_dotenv()

DEFAULT_AGENT_ID = "claudecode-skills-memanto-demo"
DEFAULT_STORE = ".memanto-skills-local.jsonl"


@dataclass
class SkillMemory:
    memory_type: str
    title: str
    content: str
    skill: str
    path_hint: str
    confidence: float = 0.9


class MemoryBackend(Protocol):
    def remember(self, memory: SkillMemory) -> None: ...

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]: ...


class LocalJsonlBackend:
    """Credential-free backend used by tests and reviewer demos."""

    def __init__(self, path: str | Path = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def remember(self, memory: SkillMemory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(memory), sort_keys=True) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]:
        memories = self._load()
        query_terms = _tokens(query)
        scored = []
        for memory in memories:
            haystack = " ".join(
                [memory.title, memory.content, memory.skill, memory.path_hint]
            )
            score = len(query_terms & _tokens(haystack))
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def _load(self) -> list[SkillMemory]:
        if not self.path.exists():
            return []
        memories = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                memories.append(SkillMemory(**json.loads(line)))
        return memories


class MemantoBackend:
    """Live backend that uses the Memanto SDK when MOORCHEH_API_KEY is available."""

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT_ID) -> None:
        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="project",
                description="Cross-skill developer memory for Claude Code skills.",
            )
        except AgentAlreadyExistsError:
            pass
        self.client.activate_agent(agent_id, duration_hours=6)

    def remember(self, memory: SkillMemory) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=["claudecode-skills", memory.skill, memory.path_hint],
            source="claude-code-skill-hook",
            provenance="skill_transcript",
        )

    def recall(self, query: str, limit: int = 5) -> list[SkillMemory]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        memories = []
        for item in result.get("memories", []):
            memories.append(
                SkillMemory(
                    memory_type=item.get("type", "memory"),
                    title=item.get("title", "Memanto memory"),
                    content=item.get("content") or item.get("title") or "",
                    skill="memanto",
                    path_hint="",
                    confidence=float(item.get("confidence", 0.9)),
                )
            )
        return memories


def build_backend() -> MemoryBackend:
    backend = os.getenv("MEMANTO_SKILLS_BACKEND", "local").lower()
    if backend == "memanto":
        api_key = os.getenv("MOORCHEH_API_KEY")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for memanto backend.")
        return MemantoBackend(
            api_key=api_key,
            agent_id=os.getenv("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID),
        )
    return LocalJsonlBackend(os.getenv("MEMANTO_SKILLS_STORE", DEFAULT_STORE))


def pre_skill_context(
    backend: MemoryBackend,
    skill: str,
    prompt: str,
    path_hint: str = "",
    limit: int = 3,
) -> str:
    query = f"{skill} {path_hint} {prompt}"
    memories = backend.recall(query, limit=limit)
    if not memories:
        return ""
    lines = [
        "Relevant engineering memory from previous skill sessions:",
        *[f"- {memory.title}: {memory.content}" for memory in memories],
    ]
    return "\n".join(lines)


def post_skill_capture(
    backend: MemoryBackend,
    skill: str,
    prompt: str,
    transcript: str,
    path_hint: str = "",
) -> SkillMemory:
    memory = distill_engineering_memory(skill, prompt, transcript, path_hint)
    backend.remember(memory)
    return memory


def distill_engineering_memory(
    skill: str,
    prompt: str,
    transcript: str,
    path_hint: str = "",
) -> SkillMemory:
    """Extract a compact engineering preference from one skill session."""

    text = f"{prompt}\n{transcript}"
    explicit = _find_explicit_decision(text)
    if explicit:
        title = "Architecture decision"
        content = explicit
        memory_type = "decision"
    else:
        title = f"{skill} session preference"
        content = _first_sentence(transcript) or _first_sentence(prompt)
        memory_type = "preference"
    return SkillMemory(
        memory_type=memory_type,
        title=title,
        content=content,
        skill=skill,
        path_hint=path_hint,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memanto memory bridge for skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre = subparsers.add_parser("pre", help="Recall context before a skill starts.")
    pre.add_argument("--skill", required=True)
    pre.add_argument("--prompt", required=True)
    pre.add_argument("--path", default="")

    post = subparsers.add_parser("post", help="Store context after a skill finishes.")
    post.add_argument("--skill", required=True)
    post.add_argument("--prompt", required=True)
    post.add_argument("--transcript", required=True)
    post.add_argument("--path", default="")

    args = parser.parse_args(argv)
    backend = build_backend()

    if args.command == "pre":
        print(pre_skill_context(backend, args.skill, args.prompt, args.path))
        return 0

    memory = post_skill_capture(
        backend, args.skill, args.prompt, args.transcript, args.path
    )
    print(f"Stored {memory.memory_type}: {memory.content}")
    return 0


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9_/-]+", value.lower()) if len(token) > 2
    }


def _find_explicit_decision(text: str) -> str:
    patterns = [
        r"(?:decision|we decided|use|prefer|choose|keep):?\s+(.+)",
        r"(?:architecture rule):?\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _first_sentence(match.group(1))
    return ""


def _first_sentence(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return ""
    return re.split(r"(?<=[.!?])\s+", cleaned)[0][:240]


if __name__ == "__main__":
    sys.exit(main())

"""Memanto-backed memory bridge for command-style Claude Code skills.

The example is intentionally dependency-light. It runs in a local preview mode
for reviewers without credentials, and can delegate storage/retrieval to the
`memanto` CLI when `SKILL_MEMORY_BACKEND=memanto` is set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

MEMORY_TYPES = {
    "artifact",
    "context",
    "decision",
    "fact",
    "goal",
    "instruction",
    "learning",
    "observation",
    "preference",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())}


@dataclass
class SkillRun:
    """A single completed skill invocation."""

    skill: str
    task: str
    output: str
    cwd: str = "."
    files: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: Path) -> "SkillRun":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            skill=str(payload["skill"]),
            task=str(payload["task"]),
            output=str(payload.get("output", "")),
            cwd=str(payload.get("cwd", ".")),
            files=list(payload.get("files", [])),
        )


@dataclass
class EngineeringMemory:
    """Reviewable memory item extracted from a skill run."""

    text: str
    memory_type: str
    skill: str
    task: str
    cwd: str
    files: list[str]
    created_at: str = field(default_factory=utc_now)
    confidence: float = 0.74

    def to_memanto_text(self) -> str:
        files = ", ".join(self.files) if self.files else "none"
        return (
            f"[{self.memory_type}] {self.text} "
            f"(source_skill={self.skill}; cwd={self.cwd}; files={files})"
        )


class MemoryBackend(Protocol):
    def remember(self, memory: EngineeringMemory) -> None:
        ...

    def recall(self, query: str, limit: int) -> list[EngineeringMemory]:
        ...


class LocalJsonBackend:
    """Small deterministic backend used for docs, CI, and credential-free review."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[EngineeringMemory]:
        if not self.path.exists():
            return []
        return [
            EngineeringMemory(**item)
            for item in json.loads(self.path.read_text(encoding="utf-8") or "[]")
        ]

    def _write(self, memories: Iterable[EngineeringMemory]) -> None:
        payload = [asdict(memory) for memory in memories]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def remember(self, memory: EngineeringMemory) -> None:
        memories = self._read()
        memory_key = (
            memory.text.strip().lower(),
            memory.memory_type,
            memory.skill,
            tuple(memory.files),
        )
        existing = {
            (item.text.strip().lower(), item.memory_type, item.skill, tuple(item.files))
            for item in memories
        }
        if memory_key not in existing:
            memories.append(memory)
            self._write(memories)

    def recall(self, query: str, limit: int) -> list[EngineeringMemory]:
        query_tokens = tokenize(query)
        scored: list[tuple[int, str, EngineeringMemory]] = []
        for memory in self._read():
            haystack = " ".join([memory.text, memory.task, memory.cwd, *memory.files])
            score = len(query_tokens & tokenize(haystack))
            if score:
                scored.append((score, memory.created_at, memory))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [memory for _, _, memory in scored[:limit]]


class MemantoSdkBackend:
    """Optional live backend that uses Memanto's Python SDK client."""

    def __init__(self, agent_id: str | None = None) -> None:
        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        config = ConfigManager()
        api_key = os.getenv("MOORCHEH_API_KEY") or config.get_api_key()
        if not api_key:
            raise RuntimeError(
                "MOORCHEH_API_KEY is not configured. Use local preview mode or run `memanto`."
            )

        active_agent_id, active_session_token = config.get_active_session()
        self.agent_id = agent_id or os.getenv("MEMANTO_AGENT_ID") or active_agent_id
        if not self.agent_id:
            raise RuntimeError(
                "No Memanto agent is active. Run `memanto agent create <name>` "
                "or set MEMANTO_AGENT_ID."
            )

        self.client = SdkClient(api_key)
        if active_session_token:
            self.client.session_token = active_session_token
            self.client.agent_id = self.agent_id

    def remember(self, memory: EngineeringMemory) -> None:
        title = f"{memory.skill} {memory.memory_type}: {memory.text[:60]}"
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=title[:100],
            content=memory.to_memanto_text(),
            confidence=memory.confidence,
            tags=["claude-code-skill", memory.skill.strip("/")],
            source="claudecode-skills-memanto",
        )

    def recall(self, query: str, limit: int) -> list[EngineeringMemory]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        recalled: list[EngineeringMemory] = []
        for item in result.get("memories", []):
            content = (
                item.get("content")
                or item.get("text")
                or item.get("memory")
                or json.dumps(item, sort_keys=True)
            )
            recalled.append(
                EngineeringMemory(
                    text=str(content),
                    memory_type=str(item.get("type", "context")),
                    skill="memanto-sdk-recall",
                    task=query,
                    cwd=".",
                    files=[],
                    confidence=float(item.get("confidence", 0.6) or 0.6),
                )
            )
        return recalled


class MemantoCliBackend:
    """Optional fallback backend that shells out to the installed memanto CLI."""

    def remember(self, memory: EngineeringMemory) -> None:
        command = [
            "memanto",
            "remember",
            memory.to_memanto_text(),
            "--type",
            memory.memory_type,
        ]
        subprocess.run(command, check=True, text=True, capture_output=True)

    def recall(self, query: str, limit: int) -> list[EngineeringMemory]:
        command = ["memanto", "recall", query, "--limit", str(limit)]
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
        return [
            EngineeringMemory(
                text=line.strip(),
                memory_type="context",
                skill="memanto-recall",
                task=query,
                cwd=".",
                files=[],
                confidence=0.6,
            )
            for line in completed.stdout.splitlines()
            if line.strip()
        ]


def build_backend() -> MemoryBackend:
    backend = os.getenv("SKILL_MEMORY_BACKEND", "local")
    if backend == "memanto-sdk":
        return MemantoSdkBackend()
    if backend == "memanto-cli":
        return MemantoCliBackend()
    default_path = Path(".memanto-skill-memory/local-preview.json")
    return LocalJsonBackend(Path(os.getenv("SKILL_MEMORY_FILE", default_path)))


def classify_memory(sentence: str) -> str:
    lowered = sentence.lower()
    if any(word in lowered for word in ("prefer", "always", "avoid", "must", "never")):
        return "instruction"
    if any(word in lowered for word in ("decision", "decided", "choose", "selected", "architecture")):
        return "decision"
    if any(word in lowered for word in ("bug", "error", "fails", "regression")):
        return "learning"
    if any(word in lowered for word in ("file", "module", "component", "api", "route")):
        return "context"
    return "observation"


def split_signal(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    candidates = re.split(r"(?<=[.!?])\s+|(?:\n\s*[-*]\s+)", normalized)
    return [candidate.strip(" -") for candidate in candidates if len(candidate.strip()) >= 24]


def extract_memories(run: SkillRun, max_items: int = 6) -> list[EngineeringMemory]:
    memories: list[EngineeringMemory] = []
    source = f"{run.task}. {run.output}"
    for sentence in split_signal(source):
        memory_type = classify_memory(sentence)
        if memory_type not in MEMORY_TYPES:
            memory_type = "observation"
        memories.append(
            EngineeringMemory(
                text=sentence[:420],
                memory_type=memory_type,
                skill=run.skill,
                task=run.task,
                cwd=run.cwd,
                files=run.files,
            )
        )
        if len(memories) >= max_items:
            break
    return memories


def render_injected_context(memories: list[EngineeringMemory]) -> str:
    if not memories:
        return "No relevant Memanto skill memories found."
    lines = ["Memanto recalled these engineering constraints from prior skills:"]
    for index, memory in enumerate(memories, start=1):
        files = f" files={','.join(memory.files)}" if memory.files else ""
        lines.append(f"{index}. ({memory.memory_type}) {memory.text}{files}")
    return "\n".join(lines)


def pre_skill(args: argparse.Namespace) -> int:
    backend = build_backend()
    query = " ".join(part for part in [args.skill, args.task, args.cwd, *args.files] if part)
    print(render_injected_context(backend.recall(query, args.limit)))
    return 0


def post_skill(args: argparse.Namespace) -> int:
    backend = build_backend()
    run = SkillRun.from_json(Path(args.run_json))
    memories = extract_memories(run, args.max_items)
    for memory in memories:
        backend.remember(memory)
    print(f"Stored {len(memories)} Memanto skill memories for {run.skill}.")
    return 0


def demo(args: argparse.Namespace) -> int:
    backend = LocalJsonBackend(Path(args.memory_file))
    first_run = SkillRun(
        skill="/grill-with-docs",
        task="Review the auth refactor plan for a FastAPI service.",
        output=(
            "Decision: keep authentication middleware stateless and push tenant "
            "lookup into a small dependency. Avoid global mutable caches because "
            "tests run with parallel workers. The auth module owns token parsing."
        ),
        cwd="services/api",
        files=["services/api/auth.py", "services/api/dependencies.py"],
    )
    for memory in extract_memories(first_run):
        backend.remember(memory)

    second_query = "Use /tdd to implement auth dependency tests in services/api"
    print(render_injected_context(backend.recall(second_query, limit=5)))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(required=True)

    pre = subcommands.add_parser("pre-skill", help="Print context to inject before a skill")
    pre.add_argument("--skill", required=True)
    pre.add_argument("--task", required=True)
    pre.add_argument("--cwd", default=".")
    pre.add_argument("--files", nargs="*", default=[])
    pre.add_argument("--limit", type=int, default=5)
    pre.set_defaults(func=pre_skill)

    post = subcommands.add_parser("post-skill", help="Store memories after a skill")
    post.add_argument("--run-json", required=True)
    post.add_argument("--max-items", type=int, default=6)
    post.set_defaults(func=post_skill)

    demo_command = subcommands.add_parser("demo", help="Run the credential-free demo")
    demo_command.add_argument(
        "--memory-file",
        default=".memanto-skill-memory/demo.json",
        help="Local JSON memory file used by the preview backend",
    )
    demo_command.set_defaults(func=demo)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

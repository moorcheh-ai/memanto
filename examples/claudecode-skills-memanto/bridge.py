#!/usr/bin/env python3
"""Claude Code skills memory bridge for Memanto.

The bridge has two execution modes:

* ``local`` stores memories in a JSON file so reviewers can run the example
  without credentials.
* ``memanto`` shells out to the installed ``memanto`` CLI and uses the active
  Memanto agent configured in the user's environment.
* ``sdk`` calls Memanto's in-repo ``SdkClient`` directly for applications that
  want to bypass shell commands while still using the real Moorcheh backend.

Both modes expose the same before/after lifecycle used by Claude Code skills:
query relevant engineering memories before a skill starts, then distill the
finished transcript into typed memories after the skill completes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_STORE = Path(".memanto-skills-memory.json")
MEMORY_TYPES = {
    "decision",
    "instruction",
    "preference",
    "context",
    "learning",
    "artifact",
}


@dataclass(slots=True)
class Memory:
    content: str
    memory_type: str
    source: str
    tags: list[str]
    confidence: float = 0.82
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unsupported memory type: {self.memory_type}")
        if not self.created_at:
            self.created_at = time.time()


class Backend(Protocol):
    def remember(self, memory: Memory) -> None:
        """Persist a memory."""

    def recall(self, query: str, limit: int) -> list[Memory]:
        """Return relevant memories."""


class LocalJsonBackend:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[Memory]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Memory(**item) for item in raw]

    def _write(self, memories: Iterable[Memory]) -> None:
        payload = [asdict(memory) for memory in memories]
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def remember(self, memory: Memory) -> None:
        memories = self._read()
        memories.append(memory)
        self._write(memories)

    def recall(self, query: str, limit: int) -> list[Memory]:
        query_terms = tokenize(query)

        def score(memory: Memory) -> tuple[int, float]:
            haystack = tokenize(
                " ".join([memory.content, memory.memory_type, *memory.tags])
            )
            overlap = len(query_terms & haystack)
            return overlap, memory.created_at

        ranked = sorted(self._read(), key=score, reverse=True)
        return [memory for memory in ranked if score(memory)[0] > 0][:limit]


class MemantoCliBackend:
    def __init__(self, command: str = "memanto") -> None:
        self.command = command

    def remember(self, memory: Memory) -> None:
        cmd = [
            self.command,
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--confidence",
            str(memory.confidence),
            "--provenance",
            "skill_transcript",
            "--source",
            memory.source,
        ]
        if memory.tags:
            cmd.extend(["--tags", ",".join(memory.tags)])
        run(cmd)

    def recall(self, query: str, limit: int) -> list[Memory]:
        result = run(
            [self.command, "recall", query, "--limit", str(limit)],
            capture_output=True,
        )
        text = result.stdout.strip()
        if not text:
            return []
        return [
            Memory(
                content=line.strip(),
                memory_type="context",
                source="memanto-recall",
                tags=["live", "recall"],
            )
            for line in text.splitlines()
            if line.strip()
        ][:limit]


class MemantoSdkBackend:
    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        client: object | None = None,
    ) -> None:
        if not api_key.strip():
            raise SystemExit(
                "MOORCHEH_API_KEY is required for `--backend sdk`. "
                "Use `--backend local` for the reviewer-safe preview."
            )
        if not agent_id.strip():
            raise SystemExit(
                "MEMANTO_AGENT_ID or `--agent-id` is required for `--backend sdk`."
            )
        self.agent_id = agent_id
        self.client = client or self._build_client(api_key, agent_id)

    @staticmethod
    def _build_client(api_key: str, agent_id: str) -> object:
        try:
            from memanto.cli.client.sdk_client import SdkClient
        except ImportError as exc:
            raise SystemExit(
                "Memanto SdkClient is not importable. Run this example from a "
                "Memanto checkout or install the memanto package."
            ) from exc

        client = SdkClient(api_key=api_key)
        try:
            client.activate_agent(agent_id)
        except Exception as exc:
            raise SystemExit(
                f"Could not activate Memanto agent `{agent_id}` for SDK mode. "
                "Create or configure the agent first, or use `--backend local`."
            ) from exc
        return client

    def remember(self, memory: Memory) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.content[:100],
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
            provenance="inferred",
        )

    def recall(self, query: str, limit: int) -> list[Memory]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=list(MEMORY_TYPES),
        )
        raw_memories = result.get("memories", []) if isinstance(result, dict) else []
        return [memory for memory in map(memory_from_sdk_result, raw_memories) if memory][
            :limit
        ]


def run(
    cmd: list[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            "memanto CLI was not found. Install it with `pip install memanto` "
            "or use `--backend local` for the reviewer-safe preview."
        ) from exc
    except subprocess.CalledProcessError as exc:
        if capture_output and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[a-zA-Z0-9_./-]{3,}", text)}


def select_backend(args: argparse.Namespace) -> Backend:
    if args.backend == "local":
        return LocalJsonBackend(Path(args.store))
    if args.backend == "sdk":
        return MemantoSdkBackend(
            api_key=args.moorcheh_api_key,
            agent_id=args.agent_id,
        )
    return MemantoCliBackend(args.memanto_command)


def memory_from_sdk_result(raw: object) -> Memory | None:
    if not isinstance(raw, dict):
        return None
    content = str(
        raw.get("content")
        or raw.get("text")
        or raw.get("memory")
        or raw.get("document")
        or ""
    ).strip()
    if not content:
        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            content = str(metadata.get("content") or metadata.get("text") or "").strip()
    if not content:
        return None

    memory_type = str(raw.get("type") or raw.get("memory_type") or "context")
    if memory_type not in MEMORY_TYPES:
        memory_type = "context"
    source = str(raw.get("source") or "memanto-sdk")
    raw_tags = raw.get("tags", [])
    tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
    return Memory(
        content=content,
        memory_type=memory_type,
        source=source,
        tags=tags or ["live", "sdk"],
    )


def infer_tags(skill: str, task: str, paths: list[str]) -> list[str]:
    tags = ["claudecode-skills", skill]
    tags.extend(Path(path).parts[-1] for path in paths if path)
    tags.extend(sorted(tokenize(task))[:8])
    return dedupe(tags)


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = item.strip().lower()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def distill_transcript(
    transcript: str,
    *,
    skill: str,
    task: str,
    paths: list[str],
) -> list[Memory]:
    base_tags = infer_tags(skill, task, paths)
    memories: list[Memory] = []

    patterns: list[tuple[str, str]] = [
        (r"^\s*(decision|decided)\s*[:=-]\s*(.+)$", "decision"),
        (r"^\s*(constraint|rule|must)\s*[:=-]\s*(.+)$", "instruction"),
        (r"^\s*(preference|prefer)\s*[:=-]\s*(.+)$", "preference"),
        (r"^\s*(learned|lesson)\s*[:=-]\s*(.+)$", "learning"),
        (r"^\s*(artifact|output)\s*[:=-]\s*(.+)$", "artifact"),
    ]

    for line in transcript.splitlines():
        stripped = line.strip("-* \t")
        for pattern, memory_type in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if match:
                content = f"{match.group(1).capitalize()}: {match.group(2).strip()}"
                memories.append(
                    Memory(
                        content=content,
                        memory_type=memory_type,
                        source=f"skill:{skill}",
                        tags=base_tags,
                    )
                )

    command_memories = extract_commands(transcript)
    for command in command_memories:
        memories.append(
            Memory(
                content=f"Useful command for {skill}: {command}",
                memory_type="learning",
                source=f"skill:{skill}",
                tags=[*base_tags, "command"],
                confidence=0.74,
            )
        )

    if not memories:
        summary = summarize_fallback(transcript, task)
        memories.append(
            Memory(
                content=summary,
                memory_type="context",
                source=f"skill:{skill}",
                tags=base_tags,
                confidence=0.62,
            )
        )

    return collapse_similar(memories)


def extract_commands(transcript: str) -> list[str]:
    commands: list[str] = []
    for line in transcript.splitlines():
        stripped = line.strip()
        if stripped.startswith("$ "):
            commands.append(stripped[2:])
        elif re.match(r"^(uv|python|pytest|npm|pnpm|git) ", stripped):
            commands.append(stripped)
    return commands[:6]


def summarize_fallback(transcript: str, task: str) -> str:
    words = transcript.split()
    excerpt = " ".join(words[:48])
    if len(words) > 48:
        excerpt += "..."
    return f"Context from previous skill run for task `{task}`: {excerpt}"


def collapse_similar(memories: list[Memory]) -> list[Memory]:
    result: list[Memory] = []
    seen: set[str] = set()
    for memory in memories:
        key = re.sub(r"\s+", " ", memory.content.lower()).strip()
        if key not in seen:
            result.append(memory)
            seen.add(key)
    return result


def render_context(memories: list[Memory], task: str) -> str:
    if not memories:
        return (
            "No relevant Memanto memories were found for this skill run.\n"
            f"Task: {task}\n"
        )
    lines = [
        "Memanto context for this skill run:",
        f"Task: {task}",
        "",
        "Apply these remembered engineering constraints when relevant:",
    ]
    for index, memory in enumerate(memories, start=1):
        tags = ", ".join(memory.tags[:6])
        lines.append(
            f"{index}. [{memory.memory_type}; {memory.source}; tags: {tags}] "
            f"{memory.content}"
        )
    return "\n".join(lines) + "\n"


def command_before(args: argparse.Namespace) -> int:
    backend = select_backend(args)
    query = " ".join([args.skill, args.task, *args.path])
    memories = backend.recall(query, args.limit)
    print(render_context(memories, args.task), end="")
    return 0


def command_after(args: argparse.Namespace) -> int:
    backend = select_backend(args)
    transcript = Path(args.transcript).read_text(encoding="utf-8")
    memories = distill_transcript(
        transcript,
        skill=args.skill,
        task=args.task,
        paths=args.path,
    )
    for memory in memories:
        backend.remember(memory)
    print(f"Stored {len(memories)} memory item(s) for skill `{args.skill}`.")
    for memory in memories:
        print(f"- {memory.memory_type}: {memory.content}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Memanto bridge for Claude Code skill lifecycle hooks."
    )
    parser.add_argument(
        "--backend",
        choices=["local", "memanto", "sdk"],
        default=os.environ.get("MEMANTO_SKILL_BACKEND", "local"),
    )
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--memanto-command", default=os.environ.get("MEMANTO_CLI", "memanto"))
    parser.add_argument(
        "--moorcheh-api-key",
        default=os.environ.get("MOORCHEH_API_KEY", ""),
        help="Moorcheh API key for the direct SDK backend.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_AGENT_ID", "claudecode-skills"),
        help="Memanto agent id for the direct SDK backend.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="recall memory before a skill run")
    before.add_argument("--skill", required=True)
    before.add_argument("--task", required=True)
    before.add_argument("--path", action="append", default=[])
    before.add_argument("--limit", type=int, default=5)
    before.set_defaults(func=command_before)

    after = subparsers.add_parser("after", help="store memory after a skill run")
    after.add_argument("--skill", required=True)
    after.add_argument("--task", required=True)
    after.add_argument("--transcript", required=True)
    after.add_argument("--path", action="append", default=[])
    after.set_defaults(func=command_after)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

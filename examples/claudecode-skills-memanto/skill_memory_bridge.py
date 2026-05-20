"""Active Memanto memory bridge for Claude Code style developer skills.

This example gives mattpocock-style skills a shared engineering memory:

* ``recall`` runs before a skill and injects relevant prior decisions.
* ``store`` runs after a skill and saves durable engineering context.
* live Memanto mode can use ``answer`` to distill an engineering profile.
* local JSONL mode keeps review and tests credential-free.
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
from typing import Any, Protocol

ENV_BACKEND = "MEMANTO_SKILLS_BACKEND"
ENV_CONTEXT = "MEMANTO_SKILL_CONTEXT"
ENV_STORE = "MEMANTO_SKILLS_STORE"
ENV_AGENT = "MEMANTO_SKILLS_AGENT"

MARKER_OPEN = "<memanto-engineering-memory>"
MARKER_CLOSE = "</memanto-engineering-memory>"

MEMORY_TYPES = {
    "decision",
    "preference",
    "instruction",
    "context",
    "fact",
    "goal",
    "learning",
    "artifact",
    "error",
    "event",
    "observation",
    "commitment",
    "relationship",
}


@dataclass(frozen=True)
class SkillRun:
    """Inputs and outputs for one skill execution."""

    skill: str
    task: str
    files: tuple[str, ...] = ()
    transcript: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def clean_skill(self) -> str:
        return self.skill.strip().strip("/") or "unknown"

    @property
    def query(self) -> str:
        return " ".join([self.skill, self.task, *self.files])


@dataclass
class EngineeringMemory:
    """A durable piece of engineering context."""

    content: str
    memory_type: str = "context"
    confidence: float = 0.8
    tags: tuple[str, ...] = ()
    source_skill: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json(self) -> str:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EngineeringMemory:
        return cls(
            content=str(payload.get("content", "")).strip(),
            memory_type=_valid_memory_type(str(payload.get("memory_type", "context"))),
            confidence=float(payload.get("confidence", 0.8)),
            tags=tuple(str(tag) for tag in payload.get("tags", []) if str(tag)),
            source_skill=str(payload.get("source_skill", "")),
            created_at=str(
                payload.get("created_at") or datetime.now(timezone.utc).isoformat()
            ),
        )


class MemoryBackend(Protocol):
    """Minimal backend contract used by the bridge."""

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        """Return memories relevant to a skill query."""

    def remember(self, memory: EngineeringMemory) -> None:
        """Store one durable memory."""


class LocalJsonlBackend:
    """Credential-free deterministic backend for tests and PR review."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        query_terms = _tokens(query)
        scored: list[tuple[int, str, EngineeringMemory]] = []
        for memory in self._read_all():
            haystack = " ".join(
                [memory.content, memory.memory_type, memory.source_skill, *memory.tags]
            )
            score = len(query_terms & _tokens(haystack))
            if score:
                scored.append((score, memory.created_at, memory))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [memory for _, _, memory in scored[:limit]]

    def remember(self, memory: EngineeringMemory) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(memory.to_json() + "\n")

    def _read_all(self) -> list[EngineeringMemory]:
        if not self.path.exists():
            return []
        records: list[EngineeringMemory] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(EngineeringMemory.from_dict(json.loads(line)))
        return records


class MemantoSdkBackend:
    """Live backend using the repository's Memanto Python package."""

    def __init__(self, agent_id: str | None = None) -> None:
        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        config = ConfigManager()
        api_key = os.getenv("MOORCHEH_API_KEY") or config.get_api_key()
        if not api_key:
            raise RuntimeError("Set MOORCHEH_API_KEY or run `memanto` first.")

        active_agent, active_token = config.get_active_session()
        self.agent_id = agent_id or os.getenv(ENV_AGENT) or active_agent
        if not self.agent_id:
            raise RuntimeError(
                f"No active Memanto agent. Run `memanto agent activate <agent>` "
                f"or set {ENV_AGENT}."
            )

        self.client = SdkClient(api_key)
        self.client.agent_id = self.agent_id
        self.client.session_token = active_token

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        response = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=["decision", "preference", "instruction", "context"],
        )
        return [_memory_from_memanto(item) for item in response.get("memories", [])]

    def remember(self, memory: EngineeringMemory) -> None:
        memory_type = _valid_memory_type(memory.memory_type)
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=_title(memory.content),
            content=memory.content,
            confidence=memory.confidence,
            tags=list(memory.tags),
            source=memory.source_skill or "claude-code-skills",
            provenance="inferred",
        )

    def answer(
        self,
        question: str,
        header_prompt: str = "",
        footer_prompt: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        return self.client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=limit,
            temperature=0.0,
            header_prompt=header_prompt,
            footer_prompt=footer_prompt,
        )


class MemantoCliBackend:
    """Fallback backend for users who prefer the configured Memanto CLI."""

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            check=True,
            capture_output=True,
            text=True,
        )
        memories = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if text and not text.lower().startswith(("found ", "id:", "type:")):
                memories.append(
                    EngineeringMemory(content=text, source_skill="memanto-cli")
                )
        return memories[:limit]

    def remember(self, memory: EngineeringMemory) -> None:
        subprocess.run(
            [
                "memanto",
                "remember",
                memory.content,
                "--type",
                _valid_memory_type(memory.memory_type),
                "--confidence",
                str(memory.confidence),
                "--source",
                memory.source_skill or "claude-code-skills",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


class EngineeringProfileExtractor:
    """Distill a skill transcript into durable memories."""

    def extract(self, run: SkillRun, backend: MemoryBackend) -> list[EngineeringMemory]:
        if run.transcript.strip():
            active = self._extract_with_memanto_answer(run, backend)
            if active:
                return active
        return self._extract_deterministically(run)

    def _extract_with_memanto_answer(
        self, run: SkillRun, backend: MemoryBackend
    ) -> list[EngineeringMemory]:
        answer = getattr(backend, "answer", None)
        if not callable(answer):
            return []

        prompt = (
            "Extract only durable engineering memories from this skill transcript. "
            "Return strict JSON with shape "
            '{"memories":[{"content":"...","memory_type":"decision|preference|'
            'instruction|context","confidence":0.0,"tags":["..."]}]}. '
            "Ignore ephemeral progress, logs, and secrets.\n\n"
            f"Skill: {run.skill}\nTask: {run.task}\nFiles: {', '.join(run.files)}\n"
            f"Transcript:\n{run.transcript}"
        )
        try:
            response = answer(
                prompt,
                header_prompt="You convert developer skill transcripts into typed memory.",
                footer_prompt="Return JSON only.",
                limit=10,
            )
        except Exception:
            return []

        answer_text = str(response.get("answer", ""))
        parsed = _parse_memories_json(answer_text)
        if not parsed:
            return []

        run_tags = _run_tags(run)
        memories: list[EngineeringMemory] = []
        for item in parsed:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            memory_type = _valid_memory_type(str(item.get("memory_type", "context")))
            confidence = _clamp_float(item.get("confidence", 0.82), 0.0, 1.0)
            tags = _dedupe([*item.get("tags", []), *run_tags])
            memories.append(
                EngineeringMemory(
                    content=_truncate(content, 1200),
                    memory_type=memory_type,
                    confidence=confidence,
                    tags=tuple(tags),
                    source_skill=run.skill,
                )
            )
        return _dedupe_memories(memories)[:12]

    def _extract_deterministically(self, run: SkillRun) -> list[EngineeringMemory]:
        patterns: list[tuple[re.Pattern[str], str, float]] = [
            (
                re.compile(r"^(?:[-*]\s*)?(?:Decision|Architecture):\s*(.+)$", re.I),
                "decision",
                0.88,
            ),
            (
                re.compile(r"^(?:[-*]\s*)?(?:Preference|Convention):\s*(.+)$", re.I),
                "preference",
                0.82,
            ),
            (
                re.compile(
                    r"^(?:[-*]\s*)?(?:Must|Never|Always|Constraint):\s*(.+)$", re.I
                ),
                "instruction",
                0.9,
            ),
            (
                re.compile(
                    r"^(?:[-*]\s*)?(?:Quirk|Caveat|Trade-off|Validation|Follow-up):\s*(.+)$",
                    re.I,
                ),
                "context",
                0.72,
            ),
        ]

        memories: list[EngineeringMemory] = []
        for raw_line in run.transcript.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for pattern, memory_type, confidence in patterns:
                match = pattern.match(line)
                if not match:
                    continue
                memories.append(
                    EngineeringMemory(
                        content=_truncate(match.group(1).strip(), 1200),
                        memory_type=memory_type,
                        confidence=confidence,
                        tags=tuple(_run_tags(run)),
                        source_skill=run.skill,
                    )
                )
                break
        return _dedupe_memories(memories)[:12]


class SkillMemoryBridge:
    """Coordinates recall-before and store-after skill lifecycle hooks."""

    def __init__(
        self,
        backend: MemoryBackend,
        extractor: EngineeringProfileExtractor | None = None,
    ) -> None:
        self.backend = backend
        self.extractor = extractor or EngineeringProfileExtractor()

    def before_skill(self, run: SkillRun, limit: int = 5) -> str:
        memories = self.backend.recall(run.query, limit=limit)
        block = format_context_block(memories, run)
        if block:
            os.environ[ENV_CONTEXT] = block
        return block

    def after_skill(self, run: SkillRun) -> list[EngineeringMemory]:
        memories = self.extractor.extract(run, self.backend)
        for memory in memories:
            self.backend.remember(memory)
        return memories

    def wrap_skill(
        self, run: SkillRun, command: list[str]
    ) -> subprocess.CompletedProcess[str]:
        context = self.before_skill(run)
        env = os.environ.copy()
        if context:
            env[ENV_CONTEXT] = context
            print(context)
            print()
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        transcript = "\n".join(
            part for part in [result.stdout, result.stderr] if part.strip()
        )
        self.after_skill(
            SkillRun(
                skill=run.skill,
                task=run.task,
                files=run.files,
                transcript=transcript,
                metadata=run.metadata,
            )
        )
        return result


def format_context_block(memories: list[EngineeringMemory], run: SkillRun) -> str:
    if not memories:
        return ""

    lines = [
        MARKER_OPEN,
        f"Relevant prior engineering memory for {run.skill}:",
    ]
    for memory in memories:
        label = memory.memory_type
        confidence = f"{memory.confidence:.2f}"
        lines.append(f"- [{label}, confidence {confidence}] {memory.content}")
    lines.extend(
        [
            "",
            "Treat this memory as guidance, not proof. Current repository state,",
            "program rules, and explicit user instructions win on conflict.",
            MARKER_CLOSE,
        ]
    )
    return "\n".join(lines)


def build_backend(kind: str | None = None, store: Path | None = None) -> MemoryBackend:
    backend = (kind or os.getenv(ENV_BACKEND) or "local").strip().lower()
    if backend == "sdk":
        return MemantoSdkBackend()
    if backend == "cli":
        return MemantoCliBackend()
    path = store or Path(os.getenv(ENV_STORE, ".memanto-skills-memory.jsonl"))
    return LocalJsonlBackend(path)


def _parse_memories_json(text: str) -> list[dict[str, Any]]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean.strip(), flags=re.I).strip()
        clean = re.sub(r"```$", "", clean).strip()
    if not clean.startswith("{") and "{" in clean:
        clean = clean[clean.find("{") : clean.rfind("}") + 1]
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("memories", [])
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


def _memory_from_memanto(payload: dict[str, Any]) -> EngineeringMemory:
    content = str(
        payload.get("content")
        or payload.get("text")
        or payload.get("document")
        or payload.get("title")
        or ""
    ).strip()
    return EngineeringMemory(
        content=content,
        memory_type=_valid_memory_type(str(payload.get("type", "context"))),
        confidence=_clamp_float(payload.get("confidence", 0.8), 0.0, 1.0),
        tags=tuple(str(tag) for tag in payload.get("tags", []) if str(tag)),
        source_skill=str(payload.get("source", "memanto")),
        created_at=str(
            payload.get("created_at") or datetime.now(timezone.utc).isoformat()
        ),
    )


def _run_tags(run: SkillRun) -> list[str]:
    tags = ["claude-code-skills", f"skill:{run.clean_skill}"]
    tags.extend(f"file:{path}" for path in run.files)
    for key, value in run.metadata.items():
        tags.append(f"{key}:{value}")
    return _dedupe(tags)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_./-]{3,}", text.lower())
        if token not in {"the", "and", "with", "this", "that"}
    }


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _dedupe_memories(memories: list[EngineeringMemory]) -> list[EngineeringMemory]:
    seen: set[str] = set()
    output: list[EngineeringMemory] = []
    for memory in memories:
        key = memory.content.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(memory)
    return output


def _valid_memory_type(memory_type: str) -> str:
    cleaned = memory_type.strip().lower().replace("-", "_")
    return cleaned if cleaned in MEMORY_TYPES else "context"


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.8
    return min(high, max(low, number))


def _title(text: str) -> str:
    clean = " ".join(text.split())
    return clean[:97] + "..." if len(clean) > 100 else clean


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _build_run(args: argparse.Namespace, *, transcript: bool = False) -> SkillRun:
    text = ""
    if transcript:
        text = args.transcript or ""
        if not text and args.transcript_file:
            text = Path(args.transcript_file).read_text(encoding="utf-8")
        if not text and not sys.stdin.isatty():
            text = sys.stdin.read()
    metadata = json.loads(args.metadata) if args.metadata else {}
    return SkillRun(
        skill=args.skill,
        task=args.task,
        files=tuple(args.file or ()),
        transcript=text,
        metadata=metadata,
    )


def cmd_recall(args: argparse.Namespace) -> int:
    bridge = SkillMemoryBridge(build_backend(args.backend, Path(args.store)))
    block = bridge.before_skill(_build_run(args), limit=args.limit)
    if block:
        print(block)
    return 0


def cmd_store(args: argparse.Namespace) -> int:
    bridge = SkillMemoryBridge(build_backend(args.backend, Path(args.store)))
    memories = bridge.after_skill(_build_run(args, transcript=True))
    print(f"stored_memories={len(memories)}")
    return 0


def cmd_wrap(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a command after --")
    bridge = SkillMemoryBridge(build_backend(args.backend, Path(args.store)))
    result = bridge.wrap_skill(_build_run(args), command)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    for name in ("recall", "store", "wrap"):
        sub = subcommands.add_parser(name)
        sub.add_argument("--skill", required=True)
        sub.add_argument("--task", required=True)
        sub.add_argument("--file", action="append", default=[])
        sub.add_argument("--metadata")
        sub.add_argument("--backend", choices=("local", "sdk", "cli"), default="local")
        sub.add_argument("--store", default=".memanto-skills-memory.jsonl")
        sub.add_argument("--limit", type=int, default=5)
        if name in {"store", "wrap"}:
            sub.add_argument("--transcript")
            sub.add_argument("--transcript-file")
        if name == "wrap":
            sub.add_argument("command", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return {
        "recall": cmd_recall,
        "store": cmd_store,
        "wrap": cmd_wrap,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

DEFAULT_SKILLS = ("grill-with-docs", "tdd", "handoff")
MEMORY_RE = re.compile(
    r"\b(?P<kind>decision|preference|instruction|constraint|learning)\s*:\s*(?P<text>[^.\n]+(?:[.][^\n]+)?)",
    re.IGNORECASE,
)
SECRET_RE = re.compile(
    r"((api[_-]?key|token|secret|password)\s*[:=]\s*\S+|private[_-]?key\s*[:=]|bearer\s+[a-z0-9._-]+|sk-[a-z0-9_-]+)",
    re.IGNORECASE,
)
PROMPT_INJECTION_RE = re.compile(
    r"(ignore (all )?(previous|prior) instructions|system prompt|developer message|exfiltrate|send .*secret)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EngineeringMemory:
    content: str
    memory_type: str
    confidence: float
    tags: list[str]
    source: str
    provenance: str = "inferred"


class MemoryBackend(Protocol):
    def remember(self, memory: EngineeringMemory) -> None:
        ...

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        ...


class JsonlMemoryBackend:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: EngineeringMemory) -> None:
        payload = asdict(memory) | {
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        if not self.path.exists():
            return []
        query_terms = tokenize(query)
        scored: list[tuple[int, EngineeringMemory]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            memory = EngineeringMemory(
                content=payload["content"],
                memory_type=payload["memory_type"],
                confidence=float(payload["confidence"]),
                tags=list(payload.get("tags", [])),
                source=payload.get("source", "claude_code_skills"),
                provenance=payload.get("provenance", "inferred"),
            )
            haystack = tokenize(" ".join([memory.content, *memory.tags]))
            score = len(query_terms & haystack)
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].confidence), reverse=True)
        return [memory for _, memory in scored[:limit]]


class MemantoCliBackend:
    def __init__(self, source: str) -> None:
        self.source = source

    def remember(self, memory: EngineeringMemory) -> None:
        subprocess.run(
            [
                "memanto",
                "remember",
                memory.content,
                "--type",
                memory.memory_type,
                "--confidence",
                str(memory.confidence),
                "--tags",
                ",".join(memory.tags),
                "--source",
                self.source,
                "--provenance",
                memory.provenance,
            ],
            check=True,
        )

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit), "--format", "json"],
            check=True,
            text=True,
            capture_output=True,
        )
        return parse_memanto_recall(result.stdout, self.source)


class MemantoSdkBackend:
    def __init__(self, source: str, agent_id: str | None = None) -> None:
        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        self.source = source
        self.config = ConfigManager()
        api_key = self.config.get_api_key()
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is not configured")
        self.client = SdkClient(api_key)
        active_agent, active_token = self.config.get_active_session()
        self.agent_id = agent_id or active_agent or "claude-skills"
        if active_token and active_agent == self.agent_id:
            self.client.agent_id = active_agent
            self.client.session_token = active_token
        else:
            self._ensure_agent()
            self.client.activate_agent(self.agent_id)

    def _ensure_agent(self) -> None:
        try:
            self.client.create_agent(
                self.agent_id,
                pattern="tool",
                description="Claude Code skills memory bridge",
            )
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise

    def remember(self, memory: EngineeringMemory) -> None:
        title = memory.content[:97] + "..." if len(memory.content) > 100 else memory.content
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=self.source,
            provenance=memory.provenance,
        )

    def recall(self, query: str, limit: int = 5) -> list[EngineeringMemory]:
        result = self.client.recall(agent_id=self.agent_id, query=query, limit=limit)
        return parse_memanto_rows(result.get("memories", []), self.source)


class SkillMemoryBridge:
    def __init__(self, backend: MemoryBackend, source: str) -> None:
        self.backend = backend
        self.source = source

    def before_skill(self, skill: str, task: str, cwd: str, limit: int = 5) -> str:
        query = f"{cwd} {skill} {task} architecture preference instruction decision"
        memories = self.backend.recall(query, limit=limit)
        context = format_context(memories)
        if context:
            os.environ["MEMANTO_SKILL_CONTEXT"] = context
        return context

    def after_skill(self, skill: str, task: str, cwd: str, transcript: str) -> int:
        memories = extract_engineering_memories(
            skill=skill,
            task=task,
            cwd=cwd,
            transcript=transcript,
            source=self.source,
        )
        for memory in memories:
            if not self._already_stored(memory):
                self.backend.remember(memory)
        return len(memories)

    def _already_stored(self, candidate: EngineeringMemory) -> bool:
        for memory in self.backend.recall(candidate.content, limit=3):
            if normalize(memory.content) == normalize(candidate.content):
                return True
        return False


def extract_engineering_memories(
    skill: str, task: str, cwd: str, transcript: str, source: str
) -> list[EngineeringMemory]:
    tags = sorted({safe_tag(skill), safe_tag(Path(cwd).name), "claude-code-skills"})
    memories: list[EngineeringMemory] = []
    for match in MEMORY_RE.finditer(transcript):
        kind = match.group("kind").lower()
        text = normalize(match.group("text"))
        if should_skip_memory(text):
            continue
        if not text:
            continue
        memory_type = "instruction" if kind == "constraint" else kind
        confidence = {
            "decision": 0.9,
            "instruction": 0.9,
            "preference": 0.85,
            "learning": 0.8,
        }.get(memory_type, 0.8)
        memories.append(
            EngineeringMemory(
                content=f"{text} (from /{skill}: {task})",
                memory_type=memory_type,
                confidence=confidence,
                tags=tags,
                source=source,
            )
        )
    return memories


def should_skip_memory(text: str) -> bool:
    return bool(SECRET_RE.search(text) or PROMPT_INJECTION_RE.search(text))


def format_context(memories: list[EngineeringMemory]) -> str:
    if not memories:
        return ""
    lines = ["MEMANTO_SKILL_CONTEXT:"]
    for memory in memories:
        lines.append(f"- [{memory.memory_type}] {memory.content}")
    return "\n".join(lines)


def parse_memanto_recall(raw: str, source: str) -> list[EngineeringMemory]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("memories") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return parse_memanto_rows(rows, source)


def parse_memanto_rows(rows: list[dict[str, object]], source: str) -> list[EngineeringMemory]:
    memories = []
    for row in rows:
        content = row.get("content") or row.get("text") or row.get("memory")
        if not content:
            continue
        memories.append(
            EngineeringMemory(
                content=content,
                memory_type=row.get("type") or row.get("memory_type") or "context",
                confidence=float(row.get("confidence", 0.8)),
                tags=list(row.get("tags", [])),
                source=row.get("source", source),
                provenance=row.get("provenance", "inferred"),
            )
        )
    return memories


def build_backend() -> MemoryBackend:
    source = os.environ.get("MEMANTO_SKILLS_SOURCE", "claude_code_skills")
    backend = os.environ.get("MEMANTO_SKILLS_BACKEND")
    if backend == "sdk":
        return MemantoSdkBackend(
            source=source,
            agent_id=os.environ.get("MEMANTO_SKILLS_AGENT_ID"),
        )
    if backend == "cli":
        return MemantoCliBackend(source=source)
    path = Path(
        os.environ.get(
            "MEMANTO_SKILLS_STORE",
            str(Path.home() / ".memanto" / "claude-skills-memory.jsonl"),
        )
    )
    return JsonlMemoryBackend(path)


def install_wrappers(out_dir: Path, skills: tuple[str, ...] = DEFAULT_SKILLS) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    for skill in skills:
        wrapper = out_dir / skill
        wrapper.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f'python "{script}" inject --skill "{skill}" --task "$*" --cwd "$PWD"',
                    f'echo "Run your real /{skill} command now, then paste its output into run-skill."',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        wrapper.chmod(0o755)


def write_claude_settings_snippet(out_path: Path) -> None:
    script = Path(__file__).resolve()
    payload = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {script} inject --skill claude-code --task \"$CLAUDE_USER_PROMPT\" --cwd \"$PWD\"",
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {script} run-skill --skill claude-code --task \"$CLAUDE_USER_PROMPT\" --cwd \"$PWD\" --output \"$(cat)\"",
                        }
                    ],
                }
            ],
        }
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def benchmark_repeated_instruction_reduction() -> dict[str, int | str]:
    with tempfile_store() as store:
        bridge = SkillMemoryBridge(
            JsonlMemoryBackend(store), source="claude_code_skills_benchmark"
        )
        repeated = [
            "keep payment tokens out of browser code",
            "use server actions for checkout mutations",
            "write one Playwright smoke test",
        ]
        bridge.after_skill(
            "grill-with-docs",
            "Review checkout flow",
            "demo-shop",
            "\n".join(
                [
                    f"Instruction: {repeated[0]}.",
                    f"Decision: {repeated[1]}.",
                    f"Preference: {repeated[2]}.",
                ]
            ),
        )
        context = bridge.before_skill("tdd", "Add checkout tests", "demo-shop")
        recovered = sum(1 for phrase in repeated if phrase in context)
        return {
            "baseline_repeated_instructions": len(repeated),
            "memanto_recovered_instructions": recovered,
            "manual_repetition_avoided": recovered,
            "status": "passed" if recovered == len(repeated) else "failed",
        }


class tempfile_store:
    def __enter__(self) -> Path:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "memory.jsonl"

    def __exit__(self, *args: object) -> None:
        self._tmp.cleanup()


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_/-]+", value.lower()))


def normalize(value: str) -> str:
    return " ".join(value.strip().split())


def safe_tag(value: str) -> str:
    tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return tag or "general"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inject = subparsers.add_parser("inject")
    inject.add_argument("--skill", required=True)
    inject.add_argument("--task", required=True)
    inject.add_argument("--cwd", default=os.getcwd())

    run_skill = subparsers.add_parser("run-skill")
    run_skill.add_argument("--skill", required=True)
    run_skill.add_argument("--task", required=True)
    run_skill.add_argument("--cwd", default=os.getcwd())
    run_skill.add_argument("--output", required=True)

    wrappers = subparsers.add_parser("install-wrappers")
    wrappers.add_argument("--out-dir", required=True)

    settings = subparsers.add_parser("write-claude-settings")
    settings.add_argument("--out", required=True)

    subparsers.add_parser("benchmark")

    args = parser.parse_args(argv)
    source = os.environ.get("MEMANTO_SKILLS_SOURCE", "claude_code_skills")
    bridge = SkillMemoryBridge(build_backend(), source=source)

    if args.command == "inject":
        context = bridge.before_skill(args.skill, args.task, args.cwd)
        if context:
            print(context)
        return 0
    if args.command == "run-skill":
        bridge.before_skill(args.skill, args.task, args.cwd)
        count = bridge.after_skill(args.skill, args.task, args.cwd, args.output)
        print(f"stored_memories={count}")
        return 0
    if args.command == "install-wrappers":
        install_wrappers(Path(args.out_dir))
        print(f"installed_wrappers={args.out_dir}")
        return 0
    if args.command == "write-claude-settings":
        write_claude_settings_snippet(Path(args.out))
        print(f"wrote_settings={args.out}")
        return 0
    if args.command == "benchmark":
        print(json.dumps(benchmark_repeated_instruction_reduction(), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

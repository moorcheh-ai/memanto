#!/usr/bin/env python3
"""Bridge Claude Code skill runs through Memanto memory.

The script intentionally keeps a credential-free preview path so reviewers can
exercise the lifecycle without a Moorcheh key. Live mode shells out to the
Memanto CLI only when MEMANTO_LIVE=1 is set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


STATE_DIR = Path(".memanto-skill-memory")
MEMORY_FILE = STATE_DIR / "memories.jsonl"
INJECTION_FILE = STATE_DIR / "injected-context.md"
DEFAULT_AGENT = "claude-code-skills"


@dataclass
class Memory:
    content: str
    memory_type: str
    skill: str
    task: str
    paths: list[str]
    source: str
    created_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9_./-]{3,}", text.lower())
        if word not in {"the", "and", "for", "with", "that", "this"}
    }


def classify_memory(line: str) -> str:
    lowered = line.lower()
    if any(marker in lowered for marker in ("decision:", "decided", "choose ")):
        return "decision"
    if any(marker in lowered for marker in ("prefer", "style", "convention")):
        return "preference"
    if any(marker in lowered for marker in ("must", "never", "always", "required")):
        return "instruction"
    return "context"


def extract_memories(
    transcript: str,
    *,
    skill: str,
    task: str,
    paths: list[str],
    source: str,
) -> list[Memory]:
    memories: list[Memory] = []
    seen: set[str] = set()
    durable_markers = re.compile(
        r"\b(decision|decided|prefer|preference|must|never|always|required|constraint|"
        r"tradeoff|quirk|follow-up|todo|style|convention)\b",
        re.IGNORECASE,
    )

    for raw_line in transcript.splitlines():
        line = raw_line.strip(" -\t")
        if len(line) < 24 or not durable_markers.search(line):
            continue
        memory_type = classify_memory(line)
        line = re.sub(r"^(decision|preference|must|instruction|context):\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"\s+", " ", line)
        dedupe_key = line.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        memories.append(
            Memory(
                content=line[:500],
                memory_type=memory_type,
                skill=skill,
                task=task,
                paths=paths,
                source=source,
                created_at=utc_now(),
            )
        )

    return memories[:12]


def append_preview_memories(memories: Iterable[Memory]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with MEMORY_FILE.open("a", encoding="utf-8") as fh:
        for memory in memories:
            fh.write(json.dumps(asdict(memory), ensure_ascii=False) + "\n")


def load_preview_memories() -> list[Memory]:
    if not MEMORY_FILE.exists():
        return []
    loaded: list[Memory] = []
    for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            loaded.append(Memory(**json.loads(line)))
        except (TypeError, json.JSONDecodeError):
            continue
    return loaded


def live_enabled() -> bool:
    return os.environ.get("MEMANTO_LIVE") == "1"


def memanto_available() -> bool:
    return shutil.which("memanto") is not None and bool(os.environ.get("MOORCHEH_API_KEY"))


def run_memanto(args: list[str]) -> str:
    result = subprocess.run(
        ["memanto", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def store_live_memories(memories: Iterable[Memory], agent: str) -> None:
    run_memanto(["agent", "create", agent])
    for memory in memories:
        metadata = {
            "skill": memory.skill,
            "task": memory.task,
            "paths": memory.paths,
            "source": memory.source,
        }
        run_memanto(
            [
                "remember",
                memory.content,
                "--type",
                memory.memory_type,
                "--metadata",
                json.dumps(metadata),
            ]
        )


def recall_live(task: str, paths: list[str], agent: str) -> str:
    query = " ".join([task, *paths]).strip()
    run_memanto(["agent", "create", agent])
    return run_memanto(["recall", query or task, "--limit", "5"])


def recall_preview(task: str, paths: list[str]) -> list[Memory]:
    query_words = normalize_words(" ".join([task, *paths]))
    scored: list[tuple[int, Memory]] = []
    for memory in load_preview_memories():
        haystack = " ".join(
            [memory.content, memory.skill, memory.task, " ".join(memory.paths)]
        )
        score = len(query_words & normalize_words(haystack))
        if score:
            scored.append((score, memory))
    scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    return [memory for _, memory in scored[:5]]


def write_injection(context: str, *, mode: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    body = [
        "<memanto-memory-context>",
        f"mode: {mode}",
        "Use these remembered constraints only when they are relevant to the current task.",
        "",
        context.strip() or "No relevant prior skill memories found.",
        "</memanto-memory-context>",
        "",
    ]
    INJECTION_FILE.write_text("\n".join(body), encoding="utf-8")
    print(f"Wrote {INJECTION_FILE}")


def format_preview_context(memories: list[Memory]) -> str:
    if not memories:
        return ""
    lines = []
    for memory in memories:
        path_hint = f" paths={','.join(memory.paths)}" if memory.paths else ""
        lines.append(
            f"- [{memory.memory_type}] {memory.content} "
            f"(from {memory.skill}; task={memory.task!r}{path_hint})"
        )
    return "\n".join(lines)


def command_before(args: argparse.Namespace) -> int:
    if live_enabled() and memanto_available():
        context = recall_live(args.task, args.paths, args.agent)
        write_injection(context, mode="live")
    else:
        memories = recall_preview(args.task, args.paths)
        write_injection(format_preview_context(memories), mode="preview")
    return 0


def command_after(args: argparse.Namespace) -> int:
    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"Transcript not found: {transcript_path}", file=sys.stderr)
        return 2

    transcript = transcript_path.read_text(encoding="utf-8")
    memories = extract_memories(
        transcript,
        skill=args.skill,
        task=args.task,
        paths=args.paths,
        source=str(transcript_path),
    )

    if not memories:
        print("No durable memories extracted.")
        return 0

    if live_enabled() and memanto_available():
        store_live_memories(memories, args.agent)
        print(f"Stored {len(memories)} memories in Memanto agent {args.agent!r}.")
    else:
        append_preview_memories(memories)
        print(f"Stored {len(memories)} preview memories in {MEMORY_FILE}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="recall context before a skill run")
    before.add_argument("--skill", required=True)
    before.add_argument("--task", required=True)
    before.add_argument("--paths", nargs="*", default=[])
    before.add_argument("--agent", default=DEFAULT_AGENT)
    before.set_defaults(func=command_before)

    after = subparsers.add_parser("after", help="store durable context after a skill run")
    after.add_argument("--skill", required=True)
    after.add_argument("--task", required=True)
    after.add_argument("--paths", nargs="*", default=[])
    after.add_argument("--transcript", required=True)
    after.add_argument("--agent", default=DEFAULT_AGENT)
    after.set_defaults(func=command_after)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

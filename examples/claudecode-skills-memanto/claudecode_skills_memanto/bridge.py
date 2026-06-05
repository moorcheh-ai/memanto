"""Bridge Claude Code skill runs into MEMANTO memories.

The module is intentionally dependency-free so the example can run before users
configure a Moorcheh API key. Dry-run mode writes memory candidates to JSONL;
production mode can pipe those candidates into the `memanto` CLI.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class MemoryCandidate:
    content: str
    memory_type: str
    confidence: float
    provenance: str
    source: str
    tags: tuple[str, ...]


SIGNAL_PATTERNS: tuple[tuple[re.Pattern[str], str, float, str], ...] = (
    (
        re.compile(r"^(?:architecture\s+)?decision:\s*(?P<content>.+)$", re.I),
        "decision",
        0.95,
        "observed",
    ),
    (
        re.compile(r"^user\s+preference:\s*(?P<content>.+)$", re.I),
        "preference",
        0.90,
        "explicit_statement",
    ),
    (
        re.compile(r"^preference:\s*(?P<content>.+)$", re.I),
        "preference",
        0.85,
        "observed",
    ),
    (
        re.compile(r"^codebase\s+fact:\s*(?P<content>.+)$", re.I),
        "fact",
        0.90,
        "observed",
    ),
    (
        re.compile(r"^project\s+fact:\s*(?P<content>.+)$", re.I),
        "fact",
        0.90,
        "observed",
    ),
    (
        re.compile(r"^fact:\s*(?P<content>.+)$", re.I),
        "fact",
        0.85,
        "observed",
    ),
)


def distill_memories(
    transcript_text: str,
    *,
    skill_name: str,
    project_slug: str,
) -> list[MemoryCandidate]:
    """Extract high-signal memory candidates from a skill transcript."""

    candidates: list[MemoryCandidate] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in transcript_text.splitlines():
        line = _strip_speaker(raw_line)
        if not line:
            continue

        for pattern, memory_type, confidence, provenance in SIGNAL_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            content = _clean_content(match.group("content"))
            if not content:
                break
            key = (memory_type, content.lower())
            if key in seen:
                break
            seen.add(key)
            candidates.append(
                MemoryCandidate(
                    content=content,
                    memory_type=memory_type,
                    confidence=confidence,
                    provenance=provenance,
                    source=f"claude_code:{skill_name}",
                    tags=(project_slug, f"skill-{skill_name}", memory_type),
                )
            )
            break

    return candidates


def build_additional_context(
    memories: Sequence[MemoryCandidate],
    *,
    skill_name: str,
    prompt: str,
    max_items: int = 8,
) -> str:
    """Format memories for Claude Code UserPromptSubmit hook stdout."""

    if not memories:
        return (
            f'<memanto-skill-context skill="{skill_name}">\n'
            f"Prompt: {prompt}\n"
            "No relevant MEMANTO memories were found for this skill run.\n"
            "</memanto-skill-context>"
        )

    lines = [
        f'<memanto-skill-context skill="{skill_name}">',
        f"Prompt: {prompt}",
        "Use these memories as prior engineering context before executing the skill:",
    ]
    for memory in memories[:max_items]:
        lines.append(f"- [{memory.memory_type}] {memory.content}")
    lines.append("</memanto-skill-context>")
    return "\n".join(lines)


def build_raw_context(
    recall_output: str,
    *,
    skill_name: str,
    prompt: str,
) -> str:
    return "\n".join(
        [
            f'<memanto-skill-context skill="{skill_name}">',
            f"Prompt: {prompt}",
            "Use this MEMANTO recall output as prior engineering context:",
            recall_output.strip(),
            "</memanto-skill-context>",
        ]
    )


def detect_skill_name(prompt: str) -> str | None:
    """Return the first slash skill name in a Claude Code user prompt."""

    match = re.search(r"(?<!\S)/([a-z][a-z0-9-]*)\b", prompt)
    if not match:
        return None
    return match.group(1)


def load_transcript_text(path: Path) -> str:
    """Read Claude transcript JSONL or plain text into one text stream."""

    raw = path.read_text(encoding="utf-8")
    text_parts: list[str] = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            text_parts.append(line)
            continue
        text_parts.extend(_event_text(event))
    return "\n".join(text_parts)


def write_jsonl(path: Path, memories: Iterable[MemoryCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for memory in memories:
            handle.write(json.dumps(asdict(memory), sort_keys=True) + "\n")


def remember_with_memanto(memories: Sequence[MemoryCandidate]) -> int:
    """Persist candidates through the installed MEMANTO CLI."""

    for memory in memories:
        command = [
            "memanto",
            "remember",
            memory.content,
            "--type",
            memory.memory_type,
            "--confidence",
            str(memory.confidence),
            "--provenance",
            memory.provenance,
            "--source",
            memory.source,
            "--tags",
            ",".join(memory.tags),
        ]
        subprocess.run(command, check=True)
    return len(memories)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bridge Claude Code skill transcripts into MEMANTO."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="Capture memories after a skill run")
    capture.add_argument("--transcript", type=Path, required=True)
    capture.add_argument("--skill", required=True)
    capture.add_argument("--project", required=True)
    capture.add_argument("--dry-run-output", type=Path)
    capture.add_argument(
        "--commit",
        action="store_true",
        help="Call `memanto remember` instead of only writing dry-run output.",
    )

    inject = subparsers.add_parser("inject", help="Format recalled memories for a skill")
    inject.add_argument("--memories", type=Path, required=True)
    inject.add_argument("--skill", required=True)
    inject.add_argument("--prompt", required=True)
    inject.add_argument("--max-items", type=int, default=8)

    hook_inject = subparsers.add_parser(
        "hook-inject",
        help="Read Claude Code hook JSON from stdin and emit prompt context",
    )
    hook_inject.add_argument("--memories", type=Path)
    hook_inject.add_argument("--skill")
    hook_inject.add_argument("--max-items", type=int, default=8)

    hook_capture = subparsers.add_parser(
        "hook-capture",
        help="Read Claude Code stop-hook JSON from stdin and capture memories",
    )
    hook_capture.add_argument("--transcript", type=Path)
    hook_capture.add_argument("--skill")
    hook_capture.add_argument("--project")
    hook_capture.add_argument(
        "--dry-run-output",
        type=Path,
        default=Path(".memanto/skill-candidates.jsonl"),
    )
    hook_capture.add_argument("--commit", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "capture":
        transcript_text = load_transcript_text(args.transcript)
        memories = distill_memories(
            transcript_text,
            skill_name=args.skill,
            project_slug=args.project,
        )
        if args.commit:
            remember_with_memanto(memories)
        else:
            output = args.dry_run_output or Path(".memanto-skill-candidates.jsonl")
            write_jsonl(output, memories)
        noun = "candidate" if len(memories) == 1 else "candidates"
        print(f"captured {len(memories)} memory {noun}")
        return 0

    if args.command == "inject":
        memories = _load_memory_candidates(args.memories)
        print(
            build_additional_context(
                memories,
                skill_name=args.skill,
                prompt=args.prompt,
                max_items=args.max_items,
            )
        )
        return 0

    if args.command == "hook-inject":
        payload = _read_hook_payload()
        prompt = str(payload.get("prompt") or "")
        skill_name = args.skill or detect_skill_name(prompt)
        if not skill_name:
            return 0

        if args.memories:
            memories = _load_memory_candidates(args.memories)
            print(
                build_additional_context(
                    memories,
                    skill_name=skill_name,
                    prompt=prompt,
                    max_items=args.max_items,
                )
            )
            return 0

        recall_output = _recall_with_memanto(
            query=f"{skill_name} {prompt}",
            limit=args.max_items,
        )
        if recall_output:
            print(build_raw_context(recall_output, skill_name=skill_name, prompt=prompt))
        return 0

    if args.command == "hook-capture":
        payload = _read_hook_payload()
        transcript_path = args.transcript or _optional_path(payload.get("transcript_path"))
        if not transcript_path or not transcript_path.exists():
            return 0
        prompt = str(payload.get("prompt") or "")
        skill_name = args.skill or detect_skill_name(prompt) or "unknown-skill"
        project_slug = args.project or Path.cwd().name
        memories = distill_memories(
            load_transcript_text(transcript_path),
            skill_name=skill_name,
            project_slug=project_slug,
        )
        if args.commit:
            remember_with_memanto(memories)
        else:
            write_jsonl(args.dry_run_output, memories)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _load_memory_candidates(path: Path) -> list[MemoryCandidate]:
    memories: list[MemoryCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        payload["tags"] = tuple(payload.get("tags", ()))
        memories.append(MemoryCandidate(**payload))
    return memories


def _read_hook_payload() -> dict[str, object]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _recall_with_memanto(query: str, *, limit: int) -> str:
    command = ["memanto", "recall", query, "--limit", str(limit)]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _strip_speaker(line: str) -> str:
    stripped = line.strip()
    return re.sub(r"^(?:User|Assistant|System|Tool)\s*:\s*", "", stripped, flags=re.I)


def _clean_content(content: str) -> str:
    return content.strip().strip("\"'` ")


def _event_text(event: object) -> list[str]:
    if not isinstance(event, dict):
        return []

    message = event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return [content]
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            return texts

    if isinstance(event.get("text"), str):
        return [event["text"]]
    return []


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

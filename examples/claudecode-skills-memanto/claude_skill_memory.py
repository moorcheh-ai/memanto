from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*=\s*['\"]?[^'\"\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
]

MEMORY_PATTERNS = [
    (
        "decision",
        re.compile(r"(?im)^\s*(?:decision:|we decided to|decided to|use)\s+(.+)$"),
    ),
    ("preference", re.compile(r"(?im)^\s*(?:prefer|preference:)\s+(.+)$")),
    ("instruction", re.compile(r"(?im)^\s*(?:always|never|avoid|must)\s+(.+)$")),
    ("context", re.compile(r"(?im)^\s*(?:in this repo|convention:|note:)\s+(.+)$")),
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryRecord:
    kind: str
    text: str
    cwd: str
    skill: str
    created_at: str
    source: str = "claude-code-hook"


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def distill_memories(
    transcript: str, cwd: str, skill: str = "unknown"
) -> list[MemoryRecord]:
    redacted = redact_secrets(transcript)
    memories: list[MemoryRecord] = []
    seen: set[tuple[str, str]] = set()
    now = datetime.now(UTC).isoformat()

    for kind, pattern in MEMORY_PATTERNS:
        for match in pattern.finditer(redacted):
            text = match.group(1).strip()
            if not text.endswith("."):
                text += "."
            key = (kind, text.lower())
            if key in seen:
                continue
            seen.add(key)
            memories.append(
                MemoryRecord(
                    kind=kind,
                    text=text,
                    cwd=cwd,
                    skill=skill,
                    created_at=now,
                )
            )
    return memories


def load_records(store_path: str | Path) -> list[MemoryRecord]:
    path = Path(store_path)
    if not path.exists():
        return []

    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            records.append(MemoryRecord(**data))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "Skipping malformed memory record in %s: %s",
                path,
                exc,
            )
    return records


def append_records(store_path: str | Path, records: list[MemoryRecord]) -> None:
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        (record.kind, record.text.lower(), record.cwd) for record in load_records(path)
    }
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            key = (record.kind, record.text.lower(), record.cwd)
            if key in existing:
                continue
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            existing.add(key)


def sync_records_to_memanto(records: list[MemoryRecord]) -> int:
    """Optionally mirror local hook memories into real Memanto.

    The example is reviewer-safe by default: it always works with local JSONL
    storage and only touches the network when MEMANTO_SYNC=1 and a Moorcheh key
    are present.
    """
    if os.environ.get("MEMANTO_SYNC") != "1":
        return 0

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        return 0

    from memanto.cli.client.sdk_client import SdkClient

    agent_id = os.environ.get("MEMANTO_AGENT_ID", "claude-code-skills")
    client = SdkClient(api_key=api_key)
    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="hook",
            description="Claude Code developer skills engineering memory",
        )
    except Exception as exc:
        message = str(exc).lower()
        if "already" not in message and "exist" not in message and "409" not in message:
            logger.warning(
                "Memanto agent creation failed for %s with %s: %s",
                agent_id,
                type(exc).__name__,
                exc,
            )
            raise
    client.activate_agent(agent_id, duration_hours=8)

    synced = 0
    for record in records:
        client.remember(
            agent_id=agent_id,
            memory_type=record.kind,
            title=record.text[:100],
            content=record.text,
            confidence=0.9,
            tags=["claude-code", "skills", record.skill],
            source=record.source,
            provenance=f"cwd:{record.cwd}",
        )
        synced += 1
    return synced


def score_record(record: MemoryRecord, prompt: str, cwd: str, path_hint: str) -> int:
    haystack = f"{prompt} {path_hint}".lower()
    score = 0
    if record.cwd == cwd:
        score += 3
    if record.kind in {"decision", "instruction", "preference"}:
        score += 2
    for token in re.findall(r"[a-zA-Z0-9_/-]{4,}", record.text.lower()):
        if token in haystack:
            score += 1
    return score


def recall_context(
    event: dict[str, Any], store_path: str | Path, limit: int = 6
) -> str:
    prompt = str(event.get("prompt") or event.get("user_prompt") or "")
    cwd = str(event.get("cwd") or "")
    tool_input = event.get("tool_input") or {}
    path_hint = str(tool_input.get("file_path") or tool_input.get("path") or "")
    scored = [
        (score_record(record, prompt, cwd, path_hint), record)
        for record in load_records(store_path)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [record for score, record in scored if score > 0][:limit]

    if not selected:
        return ""

    lines = [
        "Memanto engineering memory for this skill run:",
        *[f"- [{record.kind}] {record.text}" for record in selected],
    ]
    return "\n".join(lines)


def handle_hook_event(event: dict[str, Any], store_path: str | Path) -> dict[str, Any]:
    name = event.get("hook_event_name") or event.get("event")
    cwd = str(event.get("cwd") or "")
    skill = str(event.get("skill") or event.get("command") or "unknown")

    if name == "Stop":
        transcript = str(event.get("transcript") or event.get("conversation") or "")
        memories = distill_memories(transcript, cwd=cwd, skill=skill)
        append_records(store_path, memories)
        synced = sync_records_to_memanto(memories)
        return {
            "stored": len(memories),
            "syncedToMemanto": synced,
            "suppressOutput": False,
        }

    if name in {"UserPromptSubmit", "UserPromptExpansion", "SessionStart"}:
        context = recall_context(event, store_path)
        return {
            "suppressOutput": False,
            "hookSpecificOutput": {
                "hookEventName": name,
                "additionalContext": context,
            },
        }

    return {"suppressOutput": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code skills Memanto hook demo")
    parser.add_argument("--store", default=".claude-memanto-memory.jsonl")
    parser.add_argument(
        "--event-file",
        help="Read a Claude Code hook event JSON file. Defaults to stdin.",
    )
    args = parser.parse_args(argv)

    if args.event_file:
        event = json.loads(Path(args.event_file).read_text())
    else:
        event = json.loads(sys.stdin.read())
    print(json.dumps(handle_hook_event(event, args.store), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

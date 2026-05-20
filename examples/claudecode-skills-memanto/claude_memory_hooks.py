"""Claude Code hook bridge for mattpocock-style skills and Memanto.

The example is intentionally dependency-light for reviewers: local JSONL mode
exercises the complete hook lifecycle without private API keys, while SDK mode
uses the real Memanto client when Moorcheh credentials are present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

DEFAULT_AGENT_ID = "claude-code-skills"
DEFAULT_LIMIT = 5
DEFAULT_STORE = Path.home() / ".memanto" / "claude-code-skills-memory.jsonl"
CONTEXT_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PostToolBatch",
    "SubagentStart",
}
CAPTURE_EVENTS = {"Stop", "SessionEnd", "PostToolUse", "PostToolBatch"}
STOPWORDS = {
    "about",
    "after",
    "again",
    "because",
    "before",
    "branch",
    "current",
    "decision",
    "during",
    "implementation",
    "prefer",
    "should",
    "their",
    "there",
    "these",
    "thing",
    "using",
    "where",
    "which",
    "with",
}


class MemoryStore(Protocol):
    def add(self, memory: dict[str, Any]) -> bool:
        """Store one memory. Return True when it was newly stored."""

    def search(
        self, query: str, *, cwd: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Return memories ranked for a hook event."""


@dataclass(frozen=True)
class HookEvent:
    name: str
    session_id: str
    cwd: str | None
    transcript_path: str | None
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HookEvent:
        return cls(
            name=str(payload.get("hook_event_name") or payload.get("event") or ""),
            session_id=str(payload.get("session_id") or payload.get("sessionId") or ""),
            cwd=_coerce_optional_str(payload.get("cwd")),
            transcript_path=_coerce_optional_str(payload.get("transcript_path")),
            payload=payload,
        )

    def query_text(self) -> str:
        parts = [
            self.name,
            self.cwd or "",
            _coerce_optional_str(self.payload.get("prompt")) or "",
            _coerce_optional_str(self.payload.get("command_name")) or "",
            _coerce_optional_str(self.payload.get("command_args")) or "",
            _coerce_optional_str(self.payload.get("tool_name")) or "",
            _extract_text(self.payload.get("summary")),
            _extract_text(self.payload.get("tool_input")),
            _extract_text(self.payload.get("tool_response")),
            _extract_text(self.payload.get("tool_calls")),
        ]
        return "\n".join(part for part in parts if part)


class LocalMemoryStore:
    """Tiny JSONL backend for credential-free hook validation."""

    def __init__(self, path: Path = DEFAULT_STORE) -> None:
        self.path = path

    def add(self, memory: dict[str, Any]) -> bool:
        normalized = dict(memory)
        normalized.setdefault("created_at", _now_iso())
        normalized.setdefault("tags", [])
        normalized.setdefault("confidence", 0.75)
        normalized["id"] = normalized.get("id") or _fingerprint(
            normalized.get("type", ""),
            normalized.get("content", ""),
            normalized.get("cwd", ""),
        )

        existing_ids = {item.get("id") for item in self._read_all()}
        if normalized["id"] in existing_ids:
            return False

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, sort_keys=True) + "\n")
        return True

    def search(
        self, query: str, *, cwd: str | None, limit: int
    ) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        cwd_parts = set(_path_tokens(cwd))
        ranked: list[tuple[float, dict[str, Any]]] = []

        for memory in self._read_all():
            memory_tokens = _tokens(
                " ".join(
                    [
                        str(memory.get("title", "")),
                        str(memory.get("content", "")),
                        " ".join(map(str, memory.get("tags", []))),
                        str(memory.get("cwd", "")),
                    ]
                )
            )
            if not query_tokens:
                overlap = 0
            else:
                overlap = len(query_tokens & memory_tokens)
            path_boost = 1.5 if cwd_parts & set(_path_tokens(memory.get("cwd"))) else 0
            type_boost = 0.6 if memory.get("type") in {"instruction", "decision"} else 0
            confidence = float(memory.get("confidence", 0.7))
            score = overlap + path_boost + type_boost + confidence
            if overlap or path_boost:
                ranked.append((score, memory))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        memories: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                memories.append(record)
        return memories


class SdkMemoryStore:
    """Direct Memanto SDK backend used outside credential-free review."""

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT_ID) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key)
        self._ensure_agent()

    def add(self, memory: dict[str, Any]) -> bool:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=str(memory.get("type", "context")),
            title=str(memory.get("title", "Claude Code skill memory"))[:100],
            content=str(memory.get("content", "")),
            confidence=float(memory.get("confidence", 0.75)),
            tags=list(memory.get("tags", [])),
            source="claude-code-hooks",
            provenance="observed",
        )
        return True

    def search(
        self, query: str, *, cwd: str | None, limit: int
    ) -> list[dict[str, Any]]:
        search_query = f"{query}\nworkspace: {cwd or ''}".strip()
        result = self.client.recall(
            agent_id=self.agent_id,
            query=search_query,
            limit=limit,
        )
        return [_normalize_sdk_memory(item) for item in result.get("memories", [])]

    def _ensure_agent(self) -> None:
        try:
            self.client.get_agent(self.agent_id)
        except Exception:
            self.client.create_agent(
                self.agent_id,
                pattern="tool",
                description="Claude Code skills cross-session engineering memory",
            )
        self.client.activate_agent(self.agent_id)


def build_context(
    event: HookEvent,
    store: MemoryStore,
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    matches = store.search(event.query_text(), cwd=event.cwd, limit=limit)
    if not matches:
        return {"suppressOutput": True}

    additional_context = format_context(matches)
    return {
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": event.name,
            "additionalContext": additional_context,
        },
    }


def capture_memories(event: HookEvent, store: MemoryStore) -> int:
    text = "\n".join(
        part
        for part in [
            event.query_text(),
            read_transcript_text(event.transcript_path),
        ]
        if part
    )
    memories = distill_memories(
        text,
        source_event=event.name,
        session_id=event.session_id,
        cwd=event.cwd,
    )
    stored = 0
    for memory in memories:
        if store.add(memory):
            stored += 1
    return stored


def distill_memories(
    text: str,
    *,
    source_event: str,
    session_id: str,
    cwd: str | None,
) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if len(line) < 12:
            continue

        memory_type: str | None = None
        confidence = 0.72
        content = line

        prefixed = re.match(
            r"^(Decision|Decided|Preference|Prefer|Instruction|Rule|Caveat|Quirk|"
            r"Constraint|Gotcha|Note|Error|Fix):\s*(.+)$",
            line,
            flags=re.IGNORECASE,
        )
        if prefixed:
            label = prefixed.group(1).lower()
            content = f"{prefixed.group(1)}: {prefixed.group(2).strip()}"
            if label in {"decision", "decided"}:
                memory_type, confidence = "decision", 0.88
            elif label in {"preference", "prefer"}:
                memory_type, confidence = "preference", 0.8
            elif label in {"instruction", "rule"}:
                memory_type, confidence = "instruction", 0.92
            elif label in {"error", "fix"}:
                memory_type, confidence = "error", 0.82
            else:
                memory_type, confidence = "context", 0.74
        elif re.match(r"^(Never|Always|Must|Do not|Don't)\b", line, re.IGNORECASE):
            memory_type, confidence = "instruction", 0.94
        elif re.search(r"\bwe (will|chose|choose|decided)\b", line, re.IGNORECASE):
            memory_type, confidence = "decision", 0.78
        elif re.search(r"\b(prefer|convention|style guide)\b", line, re.IGNORECASE):
            memory_type, confidence = "preference", 0.76

        if not memory_type:
            continue

        memories.append(
            {
                "type": memory_type,
                "title": _title_for(content),
                "content": content,
                "confidence": confidence,
                "tags": _tags_for(content, cwd),
                "source_event": source_event,
                "session_id": session_id,
                "cwd": cwd,
                "created_at": _now_iso(),
            }
        )

    return _dedupe_memories(memories)


def read_transcript_text(transcript_path: str | None, *, max_lines: int = 40) -> str:
    if not transcript_path:
        return ""

    path = Path(transcript_path)
    if not path.exists():
        return ""

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    parts: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            parts.append(line)
            continue
        parts.append(_extract_text(payload))
    return "\n".join(part for part in parts if part)


def format_context(memories: list[dict[str, Any]]) -> str:
    bullets = []
    for memory in memories:
        memory_type = str(memory.get("type", "context"))
        confidence = float(memory.get("confidence", 0.75))
        content = str(memory.get("content", "")).strip()
        if not content:
            continue
        bullets.append(f"- [{memory_type} {confidence:.2f}] {content}")

    return "\n".join(
        [
            "Memanto engineering memory relevant to this Claude Code skill:",
            *bullets,
            "Apply these as constraints unless the current user prompt overrides them.",
        ]
    )


def run_benchmark() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalMemoryStore(Path(temp_dir) / "benchmark.jsonl")
        capture_memories(
            HookEvent.from_dict(
                {
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "cwd": "/repo/clinicpulse",
                    "prompt": "/grill-with-docs plan release",
                    "summary": "Decision: docs/ is local-only except tracked showcase docs.\n"
                    "Preference: verify with make verify before PR updates.\n"
                    "Never include local planning docs in public branches.",
                }
            ),
            store,
        )
        event = HookEvent.from_dict(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-2",
                "cwd": "/repo/clinicpulse",
                "prompt": "/tdd prepare public branch and PR",
            }
        )
        payload = build_context(event, store, limit=5)
        context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
        injected = context.count("\n- [")
        return {
            "sessions": 2,
            "memories_injected": injected,
            "manual_reprompt_lines_avoided": injected,
            "additional_context": context,
        }


def main(argv: list[str] | None = None, *, stdin: str | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Memanto Claude Code hooks for cross-skill engineering memory."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("inject", "capture"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--backend", choices=["local", "sdk"], default=None)
        subparser.add_argument("--store", type=Path, default=DEFAULT_STORE)
        subparser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
        subparser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)

    subparsers.add_parser("benchmark")
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        print(json.dumps(run_benchmark(), indent=2))
        return 0

    event_input = stdin if stdin is not None else sys.stdin.read()
    event = HookEvent.from_dict(json.loads(event_input or "{}"))
    store = _store_from_args(args)

    if args.command == "inject":
        if event.name not in CONTEXT_EVENTS:
            return 0
        payload = build_context(event, store, limit=args.limit)
        if payload.get("hookSpecificOutput"):
            print(json.dumps(payload))
        return 0

    if args.command == "capture":
        if event.name not in CAPTURE_EVENTS:
            print(json.dumps({"suppressOutput": True, "stored_memories": 0}))
            return 0
        stored = capture_memories(event, store)
        print(json.dumps({"suppressOutput": True, "stored_memories": stored}))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _store_from_args(args: argparse.Namespace) -> MemoryStore:
    backend = args.backend or os.getenv("MEMANTO_SKILLS_BACKEND", "local")
    if backend == "sdk":
        api_key = os.getenv("MOORCHEH_API_KEY")
        if not api_key:
            raise SystemExit("MOORCHEH_API_KEY is required for --backend sdk")
        return SdkMemoryStore(api_key=api_key, agent_id=args.agent_id)
    return LocalMemoryStore(args.store)


def _normalize_sdk_memory(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": item.get("type") or item.get("memory_type") or "context",
        "title": item.get("title") or item.get("content", "")[:80],
        "content": item.get("content") or item.get("text") or str(item),
        "confidence": item.get("confidence", item.get("score", 0.75)),
        "tags": item.get("tags", []),
    }


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_extract_text(item) for item in value)
    if isinstance(value, dict):
        parts = []
        for key in (
            "prompt",
            "command_name",
            "command_args",
            "content",
            "text",
            "summary",
            "message",
            "tool_input",
            "tool_response",
            "tool_calls",
        ):
            if key in value:
                parts.append(_extract_text(value[key]))
        return "\n".join(part for part in parts if part)
    return str(value)


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip(" \t\r\n-*`"))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
        if token not in STOPWORDS
    }


def _path_tokens(path: str | None) -> list[str]:
    if not path:
        return []
    return [part.lower() for part in Path(path).parts if part not in {"/", ""}]


def _tags_for(content: str, cwd: str | None) -> list[str]:
    tags = [token for token in _tokens(content) if len(token) <= 20][:5]
    for token in _path_tokens(cwd)[-2:]:
        if token not in tags:
            tags.append(token)
    return tags


def _title_for(content: str) -> str:
    title = re.sub(
        r"^(Decision|Preference|Instruction|Rule|Caveat|Quirk|Note):\s*", "", content
    )
    return title[:80].rstrip(".")


def _dedupe_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for memory in memories:
        key = _fingerprint(
            memory.get("type", ""), memory.get("content", ""), memory.get("cwd", "")
        )
        if key in seen:
            continue
        seen.add(key)
        memory["id"] = key
        unique.append(memory)
    return unique


def _fingerprint(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())

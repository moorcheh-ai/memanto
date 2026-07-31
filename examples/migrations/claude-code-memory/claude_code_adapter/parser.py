"""Parser for Claude Code session archives (JSONL).

Claude Code stores each interactive session as a ``.jsonl`` file under
``~/.claude/projects/<slug>/<session-id>.jsonl``. Each line is a JSON object
with a ``type`` of ``user``, ``assistant``, ``system``,
``file-history-snapshot``, or ``last-prompt``. Messages may carry a nested
``message`` object whose ``content`` is either a plain string (user turns) or
a list of typed blocks (assistant turns: ``text``, ``tool_use``,
``tool_result``).

This module normalises those archives into a small conversation model that the
memory extractor can work with, while preserving the fields that matter for
migration fidelity (session id, cwd, branch, timestamps, uuid).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Message kinds we know how to interpret.
_USER = "user"
_ASSISTANT = "assistant"
_SYSTEM = "system"
_SNAPSHOT = "file-history-snapshot"
_LAST_PROMPT = "last-prompt"

# Top-level ``type`` values that carry conversation content.
_CONTENT_TYPES = {_USER, _ASSISTANT}

# Assistant content-block kinds we care about.
_TEXT_BLOCK = "text"
_TOOL_USE_BLOCK = "tool_use"
_TOOL_RESULT_BLOCK = "tool_result"


@dataclass
class ConversationTurn:
    """One normalised message from a Claude Code session archive."""

    role: str
    text: str
    timestamp: datetime | None
    message_id: str | None
    session_id: str | None
    cwd: str | None
    git_branch: str | None
    is_meta: bool = False
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (with or without ``Z``) into aware UTC."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _extract_plain_text(content: Any) -> str:
    """Normalise Claude message content into a single plain-text string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == _TEXT_BLOCK:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text.strip())
            elif block_type in {_TOOL_USE_BLOCK, _TOOL_RESULT_BLOCK}:
                # Tool traffic is excluded from memory text; keep tool_use
                # names as diagnostics, never as durable knowledge.
                name = block.get("name")
                if block_type == _TOOL_USE_BLOCK and isinstance(name, str):
                    parts.append(f"[tool: {name}]")
        return "\n".join(part for part in parts if part).strip()
    return ""


def _extract_tool_uses(content: Any) -> list[dict[str, Any]]:
    """Return tool_use blocks (name + input) for assistant turns."""
    if not isinstance(content, list):
        return []
    uses: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == _TOOL_USE_BLOCK:
            uses.append(
                {
                    "name": block.get("name"),
                    "input": block.get("input"),
                }
            )
    return uses


def _normalise_line(raw: dict[str, Any]) -> ConversationTurn | None:
    """Convert one raw JSONL object into a ConversationTurn, or None if it
    carries no conversational content worth migrating."""
    msg_type = raw.get("type")
    if msg_type in {_SNAPSHOT, _LAST_PROMPT}:
        return None

    message = raw.get("message")
    if not isinstance(message, dict):
        message = {"role": msg_type, "content": raw.get("content")}

    role = message.get("role") or msg_type
    if role not in _CONTENT_TYPES:
        return None

    content = message.get("content")
    text = _extract_plain_text(content)
    # Skip meta/local-command wrappers that carry no durable user knowledge.
    is_meta = bool(raw.get("isMeta"))
    if is_meta and not text:
        return None

    return ConversationTurn(
        role=role,
        text=text,
        timestamp=_parse_timestamp(raw.get("timestamp")),
        message_id=str(raw.get("uuid")) if raw.get("uuid") else None,
        session_id=str(raw.get("sessionId")) if raw.get("sessionId") else None,
        cwd=str(raw.get("cwd")) if raw.get("cwd") else None,
        git_branch=str(raw.get("gitBranch")) if raw.get("gitBranch") else None,
        is_meta=is_meta,
        tool_uses=_extract_tool_uses(content),
        raw=raw,
    )


def parse_claude_jsonl(path: str | Path) -> list[ConversationTurn]:
    """Parse a Claude Code ``.jsonl`` archive into conversation turns.

    Malformed lines are skipped rather than aborting the whole archive, so a
    partially-written session can still be migrated.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Claude Code archive not found: {path}")

    turns: list[ConversationTurn] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            turn = _normalise_line(raw)
            if turn is not None:
                turns.append(turn)
    return turns


def iter_project_archives(projects_dir: str | Path) -> Iterator[Path]:
    """Yield every ``*.jsonl`` session archive under a Claude projects dir."""
    root = Path(projects_dir)
    if not root.is_dir():
        return
    yield from sorted(root.glob("**/*.jsonl"))

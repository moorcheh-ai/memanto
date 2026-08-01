#!/usr/bin/env python3
"""Convert the official ChatGPT conversations export into a portable OKF bundle.

The converter deliberately maps transcripts to `event` memories. It does not
pretend that an assistant's text is an independently verified fact; the
preceding user turn is kept alongside the response as provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
ETH_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
BTC_RE = re.compile(r"\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,90}\b")
TOKEN_RE = re.compile(
    r"\b(?:sk|pk|ghp|github_pat|xox[baprs])-?[A-Za-z0-9_\-]{16,}\b", re.IGNORECASE
)
WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Turn:
    """A text turn extracted from one exported conversation."""

    conversation_id: str
    conversation_title: str
    node_id: str
    parent_node_id: str | None
    role: str
    created_at: str | None
    text: str


@dataclass(frozen=True)
class Memory:
    """A portable event node that will become one OKF Markdown file."""

    source_id: str
    title: str
    timestamp: str | None
    content: str
    source_conversation_id: str
    source_node_id: str


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def as_iso8601(value: Any) -> str | None:
    """Return a UTC ISO-8601 value from ChatGPT's epoch-like timestamps."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return value.replace("+00:00", "Z")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def content_to_text(content: Any) -> str:
    """Read text content across known ChatGPT export content shapes."""
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if isinstance(parts, list):
        normalized: list[str] = []
        for part in parts:
            if isinstance(part, str):
                normalized.append(part)
            elif isinstance(part, dict):
                # Some exports place text in richer content parts.
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    normalized.append(text)
        return "\n".join(piece for piece in normalized if piece.strip()).strip()
    text = content.get("text")
    return text.strip() if isinstance(text, str) else ""


def resolve_export_path(export_path: Path) -> Path:
    if export_path.is_dir():
        candidate = export_path / "conversations.json"
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"No conversations.json found in {export_path}")
    if export_path.suffix.lower() != ".json":
        raise ValueError("--export must be a JSON conversations export or its containing directory")
    return export_path


def load_conversations(export_path: Path) -> list[dict[str, Any]]:
    path = resolve_export_path(export_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("conversations.json must contain a list of conversations")
    return [item for item in raw if isinstance(item, dict)]


def iter_turns(conversation: dict[str, Any]) -> Iterable[Turn]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return []
    conversation_id = str(conversation.get("id") or conversation.get("conversation_id") or "unknown")
    title = str(conversation.get("title") or "Untitled conversation").strip() or "Untitled conversation"
    turns: list[Turn] = []
    for fallback_node_id, node in mapping.items():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        if role not in {"user", "assistant"}:
            continue
        text = content_to_text(message.get("content"))
        if not text:
            continue
        node_id = str(message.get("id") or fallback_node_id)
        parent = node.get("parent")
        turns.append(
            Turn(
                conversation_id=conversation_id,
                conversation_title=title,
                node_id=node_id,
                parent_node_id=str(parent) if parent else None,
                role=role,
                created_at=as_iso8601(message.get("create_time")),
                text=text,
            )
        )
    return sorted(turns, key=lambda turn: (turn.created_at is None, turn.created_at or "", turn.node_id))


def redact(value: str) -> str:
    value = TOKEN_RE.sub("[REDACTED_TOKEN]", value)
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = ETH_RE.sub("[REDACTED_ETH_ADDRESS]", value)
    return BTC_RE.sub("[REDACTED_BTC_ADDRESS]", value)


def compact_title(value: str, max_length: int = 72) -> str:
    compact = WS_RE.sub(" ", value).strip()
    return compact if len(compact) <= max_length else compact[: max_length - 1].rstrip() + "…"


def slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:56] or "conversation"


def yaml_quote(value: str) -> str:
    """JSON string literals are valid YAML scalars and safely escape all text."""
    return json.dumps(value, ensure_ascii=False)


def make_memories(conversations: Iterable[dict[str, Any]], *, redact_output: bool) -> list[Memory]:
    memories: list[Memory] = []
    for conversation in conversations:
        turns = list(iter_turns(conversation))
        mapping = conversation.get("mapping")
        raw_nodes = mapping if isinstance(mapping, dict) else {}
        # ChatGPT's mapping uses graph node keys for `parent`, while the
        # message id may be different. Keep both aliases so context follows a
        # response's actual ancestry rather than whichever user turn happened
        # to appear earlier after timestamps are sorted.
        turn_by_id = {turn.node_id: turn for turn in turns}
        parent_by_id: dict[str, str | None] = {}
        for fallback_id, node in raw_nodes.items():
            if not isinstance(node, dict):
                continue
            fallback = str(fallback_id)
            parent = node.get("parent")
            normalized_parent = str(parent) if parent else None
            parent_by_id[fallback] = normalized_parent
            message = node.get("message")
            if isinstance(message, dict) and message.get("id"):
                message_id = str(message["id"])
                parent_by_id[message_id] = normalized_parent
                # `Turn.node_id` uses the message id, while `parent` normally
                # references the graph key. Register the graph key as an
                # alias for the extracted turn.
                candidate = turn_by_id.get(message_id)
                if candidate:
                    turn_by_id[fallback] = candidate

        def preceding_user(turn: Turn) -> str | None:
            current = parent_by_id.get(turn.node_id) or turn.parent_node_id
            visited: set[str] = set()
            while current and current not in visited:
                visited.add(current)
                candidate = turn_by_id.get(current)
                if candidate and candidate.role == "user":
                    return candidate.text
                current = parent_by_id.get(current)
            return None

        for turn in turns:
            text = redact(turn.text) if redact_output else turn.text
            if turn.role != "assistant":
                continue
            conversation_title = redact(turn.conversation_title) if redact_output else turn.conversation_title
            source_id = f"chatgpt:{turn.conversation_id}:{turn.node_id}"
            title = compact_title(f"{conversation_title}: {text.splitlines()[0]}")
            raw_context = preceding_user(turn)
            context = (
                redact(raw_context) if redact_output and raw_context else raw_context
            ) or "[No preceding user text was available in this export.]"
            body = (
                "## Conversation context\n\n"
                f"**Conversation:** {conversation_title}\n\n"
                f"**User turn:**\n\n{context}\n\n"
                "## Assistant response\n\n"
                f"{text}\n"
            )
            memories.append(
                Memory(
                    source_id=source_id,
                    title=title,
                    timestamp=turn.created_at,
                    content=body,
                    source_conversation_id=turn.conversation_id,
                    source_node_id=turn.node_id,
                )
            )
    return memories


def render_memory(memory: Memory, *, redacted: bool) -> str:
    frontmatter = [
        "---",
        "type: event",
        f"title: {yaml_quote(memory.title)}",
        "tags: [chatgpt, conversation, imported]",
    ]
    if memory.timestamp:
        frontmatter.append(f"timestamp: {memory.timestamp}")
    frontmatter.extend(
        [
            "x_memanto:",
            "  provenance: imported_conversation",
            "  source: chatgpt-data-export",
            f"  source_id: {yaml_quote(memory.source_id)}",
            f"  conversation_id: {yaml_quote(memory.source_conversation_id)}",
            f"  node_id: {yaml_quote(memory.source_node_id)}",
            f"  redacted: {'true' if redacted else 'false'}",
            "---",
            "",
            memory.content.rstrip(),
            "",
        ]
    )
    return "\n".join(frontmatter)


def write_bundle(memories: list[Memory], destination: Path, *, redacted: bool) -> dict[str, Any]:
    if destination.exists():
        shutil.rmtree(destination)
    events = destination / "memories" / "event"
    events.mkdir(parents=True)
    entries: list[dict[str, str | None]] = []
    for memory in memories:
        name = f"{slug(memory.title)}-{sha256_text(memory.source_id)[:10]}.md"
        relative_path = Path("memories") / "event" / name
        rendered = render_memory(memory, redacted=redacted)
        (destination / relative_path).write_text(rendered, encoding="utf-8", newline="\n")
        entries.append(
            {
                "source_id": memory.source_id,
                "path": relative_path.as_posix(),
                "timestamp": memory.timestamp,
                "source_sha256": sha256_text(
                    canonical_json(
                        {
                            "source_id": memory.source_id,
                            "timestamp": memory.timestamp,
                            "content": memory.content,
                        }
                    )
                ),
                "document_sha256": sha256_text(rendered),
            }
        )
    manifest = {
        "format": "chatgpt-export-to-okf/v1",
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "redacted": redacted,
        "memory_count": len(entries),
        "entries": entries,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# ChatGPT migration bundle",
        "",
        "This is a portable Open Knowledge Format bundle created from a ChatGPT data export.",
        "",
        f"- Event memories: {len(entries)}",
        f"- Redaction enabled: {'yes' if redacted else 'no'}",
        "- Integrity: see `manifest.json`",
        "",
        "## Memories",
        "",
    ]
    lines.extend(f"- [{entry['source_id']}]({entry['path']})" for entry in entries)
    (destination / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True, help="conversations.json or its containing export directory")
    parser.add_argument("--out", type=Path, required=True, help="directory to create as an OKF bundle")
    parser.add_argument("--no-redact", action="store_true", help="preserve emails, token-like strings, and crypto addresses")
    args = parser.parse_args()
    conversations = load_conversations(args.export)
    memories = make_memories(conversations, redact_output=not args.no_redact)
    manifest = write_bundle(memories, args.out, redacted=not args.no_redact)
    print(json.dumps({"okf_bundle": str(args.out), "memory_count": manifest["memory_count"], "redacted": manifest["redacted"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

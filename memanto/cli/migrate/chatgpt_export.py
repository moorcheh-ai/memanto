"""
Export a ChatGPT account archive into Memanto-compatible memory data.

ChatGPT's official data export (Settings -> Security and data controls ->
Export data) produces a ``conversations.json`` array where each conversation
is a graph of message nodes. The user's own statements -- preferences, facts,
commitments, and decisions -- are the highest-value "memory" a person carries
out of ChatGPT. This module traverses that graph, pulls the active (main)
branch of every conversation, and extracts the user-authored messages as
structured memories.

Output shape (matches the mapper contract in ``mappers.MAPPERS``):

    {
        "provider": "chatgpt",
        "exported_at": "2026-08-26T00:00:00+00:00",
        "memories": [
            {
                "id": "conversation-id:node-id",
                "content": "<the user's message text>",
                "created_at": "<unix seconds or iso>",
                "tags": ["chatgpt", "conversation:<title>"],
            },
            ...
        ],
    }

Pure stdlib -- no OpenAI SDK, no network calls. The export is a local file, so
this adapter is fully offline and reproducible.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVIDER = "chatgpt"
MAX_MESSAGE_CHARS = 4000  # keep the highest-value slice, not a wall of text
MAX_CONVERSATIONS = 1000  # cap: the graph is expensive on huge archives
MAX_PARENT_DEPTH = 2000   # hard bound on the parent walk (malformed-graph guard)


def _extract_text_parts(node: dict[str, Any]) -> str:
    """Pull the plain-text parts of one message node.

    ChatGPT stores message text in ``content.parts`` as a list that can mix
    strings with dict objects (tool calls, attachments). We keep only the
    string parts and join them; everything else (images, tool payloads) is
    intentionally dropped from the memory body but the node is still counted.
    """
    message = node.get("message") or {}
    content = message.get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, str):
            text = part.strip()
            if text:
                texts.append(text)
    return "\n\n".join(texts)


def _node_time(node: dict[str, Any]) -> int | None:
    """Best-effort ``create_time`` (unix seconds) of a message node."""
    message = node.get("message") or {}
    created = message.get("create_time")
    if isinstance(created, bool):
        # ``bool`` subclasses ``int``; without this guard, ``True``
        # becomes ``int(True)=1`` -> 1970-01-01 timestamp.
        return None
    if isinstance(created, (int, float)):
        return int(created)
    return None


def _conversation_author_message(
    conversation: dict[str, Any],
) -> Iterable[tuple[str, int | None]]:
    """Yield ``(node_id, create_time)`` for the active user-authored messages.

    ChatGPT exports preserve edits and regenerations as dead branches; the
    leaf of the currently-visible thread is the terminal node of the graph.
    Prefer ``conversation["current_node"]`` when available (it pins the
    exact thread the user last saw). Fall back to the newest leaf when
    ``current_node`` is missing or dangling. The parent walk back from that
    leaf collects user-role nodes, which mirrors how the ChatGPT UI shows
    the current thread.
    """
    mapping = conversation.get("mapping") or {}
    current_node_id = conversation.get("current_node")

    # Prefer ``current_node`` when it exists and points to a node:
    # walk from that node's parent ancestry so we export the exact thread
    # the user last saw, even if a newer regenerated leaf exists.
    leaf = None
    # Guard non-string current_node (e.g. JSON arrays) before mapping lookup:
    # non-string keys can never match, so reject them explicitly (CodeRabbit).
    if isinstance(current_node_id, str) and current_node_id in mapping:
        leaf = mapping[current_node_id]

    # Fall back to the newest leaf (original behaviour) when current_node
    # is missing, dangling, or its leaf has no parent chain.
    if leaf is None:
        candidates: list[dict[str, Any]] = []
        for node in mapping.values():
            node_id = node.get("id")
            message = node.get("message")
            if not node_id or not isinstance(message, dict):
                continue
            children = node.get("children") or []
            if not children:
                candidates.append(node)
        if not candidates:
            return
        leaf = max(candidates, key=lambda n: (_node_time(n) or 0, str(n.get("id") or "")))

    seen: set[str] = set()
    node = leaf
    depth = 0
    while node is not None:
        depth += 1
        if depth > MAX_PARENT_DEPTH:
            break
        node_id = node.get("id")
        if not isinstance(node_id, str):
            node_id = str(node_id or "")
        if not node_id:
            break
        if node_id in seen:
            break
        seen.add(node_id)
        message = node.get("message") or {}
        author = message.get("author") or {}
        role = (author.get("role") or "").lower()
        if role == "user":
            created = message.get("create_time")
            yield node_id, (int(created) if isinstance(created, (int, float)) and not isinstance(created, bool) else None)
        parent_id = node.get("parent")
        node = mapping.get(parent_id) if parent_id else None


def _conversation_export(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    """Map one conversation's user statements to memory rows."""
    title = (conversation.get("title") or "Untitled").strip()
    conversation_id = str(conversation.get("id") or "")
    memories: list[dict[str, Any]] = []

    # _conversation_author_message walks leaf -> root, which yields the
    # messages newest-first. Reverse so the export (and therefore the mapped
    # preview, import batch order, and OKF bundle) is chronological.
    author_messages = list(_conversation_author_message(conversation))
    for node_id, created in reversed(author_messages):
        node = (conversation.get("mapping") or {}).get(node_id) or {}
        text = _extract_text_parts(node)
        if not text:
            continue
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[: MAX_MESSAGE_CHARS - 4].rstrip() + "\n..."

        tags = ["chatgpt"]
        if title and title != "Untitled":
            tags.append(f"conversation:{title}")

        memories.append(
            {
                "id": f"{conversation_id}:{node_id}" if conversation_id else node_id,
                "content": text,
                "created_at": created,
                "tags": tags,
            }
        )
    return memories


def load_conversations(path: str | Path) -> list[dict[str, Any]]:
    """Load the ``conversations.json`` array from a ChatGPT data export."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # Some exports wrap the array under a ``conversations`` key. Only
        # unwrap when it actually holds a list; anything else is malformed.
        wrapped = data.get("conversations")
        if isinstance(wrapped, list):
            data = wrapped
        else:
            raise ValueError(
                "Unrecognized ChatGPT export: expected a JSON array of conversations "
                f"at {path}"
            )
    if not isinstance(data, list):
        raise ValueError(
            "Unrecognized ChatGPT export: expected a JSON array of conversations "
            f"at {path}"
        )
    return [item for item in data if isinstance(item, dict)]


def export_chatgpt_memories(
    conversations: list[dict[str, Any]],
    *,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """Turn the raw conversation array into a provider export dict."""
    rows: list[dict[str, Any]] = []
    for conversation in conversations[:MAX_CONVERSATIONS]:
        rows.extend(_conversation_export(conversation))

    if len(conversations) > MAX_CONVERSATIONS:
        print(
            f"Warning: {len(conversations)} conversations found; "
            f"only the first {MAX_CONVERSATIONS} were processed. "
            "Raise MAX_CONVERSATIONS to include the rest.",
            file=sys.stderr,
        )

    if exported_at is None:
        exported_at = datetime.now(timezone.utc).isoformat()

    return {
        "provider": PROVIDER,
        "exported_at": exported_at,
        "memories": rows,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python3 chatgpt_export.py conversations.json out.json``."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("Usage: python3 chatgpt_export.py <conversations.json> <out.json>")
        return 2
    src, dst = Path(args[0]), Path(args[1])
    try:
        conversations = load_conversations(src)
        export = export_chatgpt_memories(conversations)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    try:
        dst.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Error: cannot write {dst}: {exc}", file=sys.stderr)
        return 1
    print(
        f"Exported {len(export['memories'])} user memories "
        f"from {len(conversations)} conversations -> {dst}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
ChatGPT conversation export → Memanto migration adapter.

Parses ChatGPT's `conversations.json` export (from Settings → Data controls →
Export data) and maps each conversation turn into Memanto memory payloads
suitable for `SdkClient.batch_remember`.

ChatGPT export format (conversations.json):
[
  {
    "title": "Conversation Title",
    "create_time": 1700000000.0,
    "update_time": 1700001000.0,
    "mapping": {
      "<node_id>": {
        "id": "<uuid>",
        "message": {
          "id": "<uuid>",
          "author": {"role": "user"|"assistant"|"system"|"tool"},
          "create_time": 1700000000.0,
          "content": {
            "content_type": "text",
            "parts": ["The actual message text"]
          },
          "metadata": {...}
        },
        "parent": "<parent_node_id>",
        "children": ["<child_node_id>"]
      }
    },
    "conversation_id": "<uuid>"
  }
]

Each conversation is a tree of messages. We linearize it (follow children from
root) and extract user+assistant turns as memory-worthy content. System messages
and empty nodes are skipped.

Produces memories matching the schema in mappers.py:
    {title, content, type, tags, confidence, source, source_ref, provenance,
     created_at, updated_at}
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# -- Internal helpers --------------------------------------------------------

def _parse_dt(value: Any) -> datetime | None:
    """Parse epoch float/int or ISO string to UTC datetime."""
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _title_from(text: str, max_len: int = 80) -> str:
    """Generate a title from content, truncating cleanly."""
    clean = text.strip().replace("\n", " ")
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _linearize_conversation(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the conversation tree to produce an ordered list of messages.

    ChatGPT stores conversations as a tree (branching on edits). We follow
    the first child at each node to produce the canonical linear thread.
    """
    if not mapping:
        return []

    # Find root node (the one with no parent or parent not in mapping)
    root_id = None
    for node_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None or parent not in mapping:
            root_id = node_id
            break

    if root_id is None:
        # Fallback: pick any node and walk up (with cycle guard)
        root_id = next(iter(mapping))
        seen_up = {root_id}
        while mapping.get(root_id, {}).get("parent") in mapping:
            parent = mapping[root_id]["parent"]
            if parent in seen_up:
                break  # Cycle detected — stop walking
            seen_up.add(parent)
            root_id = parent

    # Walk down following first child
    messages = []
    current = root_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        node = mapping.get(current)
        if not node:
            break
        msg = node.get("message")
        if msg and msg.get("content"):
            messages.append(msg)
        children = node.get("children", [])
        current = children[0] if children else None

    return messages


def _extract_text(content: dict[str, Any] | None) -> str:
    """Extract text content from a ChatGPT message content object."""
    if not content:
        return ""
    if not isinstance(content, dict):
        return str(content) if content else ""
    content_type = content.get("content_type", "text")
    if content_type == "text":
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                # Multimodal: image, file, etc — extract description if present
                desc = part.get("description") or part.get("alt_text") or part.get("name")
                if desc:
                    text_parts.append(f"[{content_type}: {desc}]")
        return "\n".join(text_parts).strip()
    elif content_type in ("multimodal_text", "model_editable_context"):
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get("content_type") == "image_asset_pointer":
                text_parts.append("[image]")
        return "\n".join(text_parts).strip()
    elif content_type == "code":
        return content.get("text", "")
    return ""


# -- Main mapper function ---------------------------------------------------


def load_chatgpt_export(path: str | Path) -> dict[str, Any]:
    """Load a ChatGPT data export (conversations.json).

    Accepts either a path to `conversations.json` directly, or a directory
    containing it (the unzipped export folder).

    Returns the standard export dict shape: {"memories": [...conversations...]}.
    """
    p = Path(path)
    if p.is_dir():
        candidates = [p / "conversations.json", p / "chat.html"]
        for c in candidates:
            if c.exists():
                p = c
                break
        else:
            raise FileNotFoundError(
                f"No conversations.json found in {path}. "
                f"Expected the unzipped ChatGPT data export directory."
            )

    if not p.exists():
        raise FileNotFoundError(f"ChatGPT export not found: {path}")

    # Stream-parse for large exports (can be 100MB+)
    conversations = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(conversations, list):
        raise ValueError(
            f"Expected a JSON array of conversations, got {type(conversations).__name__}"
        )

    return {"conversations": conversations, "source_path": str(p)}


def map_chatgpt(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map ChatGPT conversation export to Memanto memory payloads.

    Each meaningful exchange (user question + assistant response) becomes one
    memory record. Pure system messages, empty messages, and tool-call nodes
    are skipped.

    Temporal metadata is fully preserved:
    - `created_at`: the message timestamp from ChatGPT
    - conversation title, turn index, and conversation_id in supporting data
    - Session boundaries (conversation titles) become tags

    Source tracking:
    - `source`: "chatgpt"
    - `source_ref`: "{conversation_id}:{message_id}" for precise traceability
    """
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    conversations = export.get("conversations", [])

    for conv in conversations:
        if not isinstance(conv, dict):
            continue

        conv_title = (conv.get("title") or "Untitled").strip()
        conv_id = conv.get("conversation_id") or conv.get("id") or ""
        conv_created = _parse_dt(conv.get("create_time"))
        mapping = conv.get("mapping") or {}

        if not mapping:
            continue

        messages = _linearize_conversation(mapping)

        # Pair user + assistant turns
        turn_index = 0
        i = 0
        while i < len(messages):
            msg = messages[i]
            author = (msg.get("author") or {}).get("role", "")
            content_text = _extract_text(msg.get("content"))

            if not content_text or author in ("system", "tool"):
                i += 1
                continue

            msg_id = msg.get("id", "")
            msg_time = _parse_dt(msg.get("create_time"))
            turn_index += 1

            # Build memory content
            if author == "user":
                # Look ahead for assistant response
                response_text = ""
                response_id = ""
                response_time = None
                if i + 1 < len(messages):
                    next_msg = messages[i + 1]
                    next_author = (next_msg.get("author") or {}).get("role", "")
                    if next_author == "assistant":
                        response_text = _extract_text(next_msg.get("content"))
                        response_id = next_msg.get("id", "")
                        response_time = _parse_dt(next_msg.get("create_time"))
                        i += 1  # consume the assistant message too

                if response_text:
                    # Full exchange: user question + assistant answer
                    content = f"Q: {content_text}\n\nA: {response_text}"
                    ref_id = f"{conv_id}:{msg_id}" if conv_id else msg_id
                else:
                    # User message without response
                    content = content_text
                    ref_id = f"{conv_id}:{msg_id}" if conv_id else msg_id

            elif author == "assistant":
                # Standalone assistant message (no preceding user msg)
                content = content_text
                ref_id = f"{conv_id}:{msg_id}" if conv_id else msg_id
            else:
                i += 1
                continue

            if not content.strip():
                i += 1
                continue

            # Determine memory type heuristic
            memory_type = None
            lower = content.lower()
            if any(kw in lower for kw in ("prefer", "always", "never", "like", "don't like")):
                memory_type = "preference"
            elif any(kw in lower for kw in ("decided", "decision", "chose", "will do")):
                memory_type = "decision"
            elif any(kw in lower for kw in ("learned", "realized", "understood", "found out")):
                memory_type = "observation"

            # Tags: conversation title as session marker
            tags = [f"session:{conv_title[:50]}"]
            if conv_title and conv_title != "Untitled":
                # Extract topic words for discoverability
                topic_tag = conv_title.lower().replace(" ", "-")[:30]
                tags.append(f"topic:{topic_tag}")

            # Supporting data footer
            footer_parts = []
            if conv_title:
                footer_parts.append(f"- Conversation: {conv_title}")
            footer_parts.append(f"- Turn: {turn_index}")
            if conv_id:
                footer_parts.append(f"- Conversation ID: {conv_id}")
            if msg_time:
                footer_parts.append(f"- Timestamp: {msg_time.isoformat()}")

            footer = ""
            if footer_parts:
                footer = "\n\n---\n[Supporting data]\n" + "\n".join(footer_parts)

            # Truncate if needed (10000 char limit from Memanto schema)
            max_content = 10000
            if footer:
                budget = max_content - len(footer)
                if len(content) > budget:
                    content = content[: budget - 4] + "\n..."
                content = content + footer
            elif len(content) > max_content:
                content = content[: max_content - 4] + "\n..."

            rows.append(
                {
                    "title": _title_from(f"[{conv_title}] {content_text[:60]}"),
                    "content": content,
                    "type": memory_type,
                    "tags": tags,
                    "confidence": 0.75,
                    "source": "chatgpt",
                    "source_ref": ref_id,
                    "provenance": "imported",
                    "created_at": msg_time or conv_created,
                    "updated_at": migrated_at,
                }
            )

            i += 1

    return rows


# -- Register in MAPPERS (to be added to mappers.py) -----------------------
# MAPPERS["chatgpt"] = map_chatgpt


# -- Self-test --------------------------------------------------------------

if __name__ == "__main__":
    # Quick validation with synthetic data
    sample_export = {
        "conversations": [
            {
                "title": "Python Help",
                "conversation_id": "conv-123",
                "create_time": 1700000000.0,
                "update_time": 1700001000.0,
                "mapping": {
                    "root": {
                        "id": "root",
                        "message": None,
                        "parent": None,
                        "children": ["msg1"],
                    },
                    "msg1": {
                        "id": "msg1",
                        "message": {
                            "id": "msg-uuid-1",
                            "author": {"role": "user"},
                            "create_time": 1700000100.0,
                            "content": {"content_type": "text", "parts": ["How do I read a JSON file in Python?"]},
                        },
                        "parent": "root",
                        "children": ["msg2"],
                    },
                    "msg2": {
                        "id": "msg2",
                        "message": {
                            "id": "msg-uuid-2",
                            "author": {"role": "assistant"},
                            "create_time": 1700000105.0,
                            "content": {"content_type": "text", "parts": ["Use json.load() with a file handle:\n\nimport json\nwith open('data.json') as f:\n    data = json.load(f)"]},
                        },
                        "parent": "msg1",
                        "children": ["msg3"],
                    },
                    "msg3": {
                        "id": "msg3",
                        "message": {
                            "id": "msg-uuid-3",
                            "author": {"role": "user"},
                            "create_time": 1700000200.0,
                            "content": {"content_type": "text", "parts": ["I prefer using pathlib for file paths"]},
                        },
                        "parent": "msg2",
                        "children": [],
                    },
                },
            }
        ]
    }

    results = map_chatgpt(sample_export)
    print(f"Mapped {len(results)} memories from {len(sample_export['conversations'])} conversations")
    print()
    for r in results:
        print(f"  [{r['type'] or 'auto'}] {r['title']}")
        print(f"    source_ref: {r['source_ref']}")
        print(f"    created_at: {r['created_at']}")
        print(f"    tags: {r['tags']}")
        print(f"    content: {r['content'][:100]}...")
        print()

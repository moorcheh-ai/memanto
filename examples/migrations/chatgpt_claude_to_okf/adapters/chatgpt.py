"""Parse a real ChatGPT (chat.openai.com) export into normalized conversations.

Real export layout (unzipped):
    chatgpt/conversations.json
        [ { "title": ..., "create_time": ..., "update_time": ...,
            "mapping": { "<node-id>": { "message": { "author": {"role": "user"|"assistant"},
                                                   "content": {"content_type": "text", "parts": ["..."]},
                                                   "create_time": ... },
                                         "parent": "<node-id>" } } }, ... ]

Tolerant fallbacks: conversations.json may also sit directly at the export root,
and some exports store text in content.parts[0] as str vs {"text": ...}.
"""
from __future__ import annotations

import json
from pathlib import Path


def _find_conversations_file(export_dir: Path) -> Path | None:
    candidates = [
        export_dir / "chatgpt" / "conversations.json",
        export_dir / "conversations.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _node_text(message: dict) -> str | None:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        return None
    texts: list[str] = []
    for p in parts:
        if isinstance(p, str):
            texts.append(p)
        elif isinstance(p, dict) and p.get("text"):
            texts.append(str(p["text"]))
    joined = "\n".join(t for t in texts if t.strip())
    return joined or None


def load_chatgpt(export_dir: str | Path) -> list[dict]:
    """Return list of conversations:
    {id, title, created, updated, source: "chatgpt", turns: [{role, text, ts}]}
    """
    export_dir = Path(export_dir)
    conv_file = _find_conversations_file(export_dir)
    if conv_file is None:
        raise FileNotFoundError(
            f"No conversations.json found under {export_dir} "
            f"(looked for chatgpt/conversations.json and conversations.json)"
        )
    data = json.loads(conv_file.read_text(encoding="utf-8"))
    conversations = []
    for conv in data:
        conv_id = str(conv.get("id") or conv.get("conversation_id") or "")
        title = conv.get("title") or conv.get("name") or f"conversation-{conv_id[:8] or len(conversations)}"
        mapping = conv.get("mapping") or {}
        turns = []
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            author = msg.get("author") or {}
            role = author.get("role")
            if role not in ("user", "assistant"):
                continue
            text = _node_text(msg)
            if not text:
                continue
            ts = msg.get("create_time")
            turns.append({"role": role, "text": text, "ts": float(ts) if isinstance(ts, (int, float)) else None})
        if not turns:
            continue
        turns.sort(key=lambda t: t["ts"] if t["ts"] is not None else 0)
        conversations.append({
            "id": conv_id or f"chatgpt-{len(conversations)}",
            "title": str(title),
            "created": conv.get("create_time"),
            "updated": conv.get("update_time"),
            "source": "chatgpt",
            "turns": turns,
        })
    return conversations

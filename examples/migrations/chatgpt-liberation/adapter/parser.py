"""ChatGPT takeout parser — conversations.json + memory.json → export dict."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    """Parse dt."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
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
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _load_json_from_zip(zpath: Path, name: str) -> Any | None:
    """Load json from zip."""
    try:
        with zipfile.ZipFile(zpath, "r") as zf:
            # handle nested path inside zip
            for info in zf.infolist():
                if info.filename.endswith(name):
                    return json.loads(zf.read(info.filename).decode("utf-8"))
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return None
    return None


def _load_json_file(path: Path) -> Any | None:
    """Load json file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_chatgpt_export(source: str | Path) -> dict[str, Any]:
    """Load a ChatGPT data export (zip or directory) into a provider export dict.

    Accepts:
    - path to ``chatgpt-export.zip``
    - path to directory containing ``conversations.json`` / ``memory.json``
    - path to a single ``conversations.json`` file (uses sibling memory if present)

    Returns ``{"conversations": [...], "memories": [...]}`` shape consumed by
    ``map_chatgpt``. Never raises on missing files — returns empty lists so the
    caller can surface a mapping summary instead of a stack trace.
    """
    p = Path(source)

    conversations: list[dict[str, Any]] = []
    explicit_memories: list[dict[str, Any]] = []

    if p.is_file() and p.suffix.lower() == ".zip":
        data = _load_json_from_zip(p, "conversations.json")
        if isinstance(data, list):
            conversations = data
        elif isinstance(data, dict) and "conversations" in data:
            conversations = data.get("conversations") or []
        mem = _load_json_from_zip(p, "memory.json")
        if isinstance(mem, list):
            explicit_memories = mem
        elif isinstance(mem, dict) and "memories" in mem:
            explicit_memories = mem.get("memories") or []
        else:
            # also try custom_instructions / personalization
            for alt in ("personalization.json", "custom_instructions.json"):
                alt_data = _load_json_from_zip(p, alt)
                if isinstance(alt_data, list):
                    explicit_memories.extend(alt_data)

    elif p.is_dir():
        conv_path = p / "conversations.json"
        mem_path = p / "memory.json"
        if conv_path.exists():
            data = _load_json_file(conv_path)
            if isinstance(data, list):
                conversations = data
            elif isinstance(data, dict):
                conversations = data.get("conversations") or data.get("memory") or []
        # memory file optional
        if mem_path.exists():
            mem = _load_json_file(mem_path)
            if isinstance(mem, list):
                explicit_memories = mem
            elif isinstance(mem, dict):
                explicit_memories = mem.get("memories") or mem.get("memory") or []

    elif p.is_file() and p.name == "conversations.json":
        data = _load_json_file(p)
        if isinstance(data, list):
            conversations = data
        elif isinstance(data, dict):
            conversations = data.get("conversations") or []
        sibling = p.parent / "memory.json"
        if sibling.exists():
            mem = _load_json_file(sibling)
            if isinstance(mem, list):
                explicit_memories = mem

    # Normalize: conversations.json from real export has title + mapping + create_time
    # Keep as-is for mapper; also add explicit_memories as synthetic conversation type
    return {
        "conversations": conversations if isinstance(conversations, list) else [],
        "memories": explicit_memories if isinstance(explicit_memories, list) else [],
    }


def extract_messages(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten conversations → ordered message records for mapping."""
    out: list[dict[str, Any]] = []
    for conv in conversations:
        conv_id = conv.get("id") or conv.get("conversation_id") or ""
        conv_title = conv.get("title") or ""
        conv_time = _parse_dt(conv.get("create_time") or conv.get("created_at"))
        mapping = conv.get("mapping") or {}
        # Real export nests messages under mapping; synthetic uses direct messages
        if isinstance(mapping, dict) and mapping:
            for node_id, node in mapping.items():
                msg = (node or {}).get("message")
                if not msg:
                    continue
                author = (msg.get("author") or {}).get("role") or msg.get("role") or ""
                content = msg.get("content") or {}
                # content may be {"parts": ["..."]} or plain string
                text = ""
                if isinstance(content, dict):
                    parts = content.get("parts") or []
                    text = "\n".join(str(p) for p in parts if p)
                    if not text:
                        text = str(content.get("text") or "")
                elif isinstance(content, str):
                    text = content
                if not text.strip():
                    continue
                out.append({
                    "conversation_id": conv_id,
                    "conversation_title": conv_title,
                    "node_id": node_id,
                    "role": author,
                    "content": text.strip(),
                    "create_time": _parse_dt(msg.get("create_time") or conv_time),
                })
        else:
            # synthetic shape: {"messages": [{role, content, create_time}]}
            for m in conv.get("messages") or []:
                text = str(m.get("content") or "").strip()
                if not text:
                    continue
                out.append({
                    "conversation_id": conv_id,
                    "conversation_title": conv_title,
                    "node_id": m.get("id") or "",
                    "role": m.get("role") or "user",
                    "content": text,
                    "create_time": _parse_dt(m.get("create_time") or conv_time),
                })
    # already chronological within each convo; sort globally by time where available
    out.sort(key=lambda r: r.get("create_time") or datetime.min.replace(tzinfo=timezone.utc))
    return out

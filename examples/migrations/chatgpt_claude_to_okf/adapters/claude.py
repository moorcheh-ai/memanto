"""Parse a real Claude.ai export into normalized conversations.

Real export layout (unzipped):
    claude/conversations.json           # index: [{uuid, name, created_at, updated_at}, ...]
    claude/<uuid>.jsonl                 # one JSON object per line, e.g.:
        { "type": "user"|"assistant", "message": {"role": ..., "content": [
              {"type": "text", "text": "..."} | {"type": "thinking", ...} ]},
          "timestamp": ..., "parent_uuid": ..., "conversation_uuid": ... }

Tolerant: index may be missing (fall back to globbing *.jsonl and using the
filename stem as uuid); content may be a plain string.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path


def _find_index(export_dir: Path) -> Path | None:
    for pattern in ("claude/conversations.json", "conversations.json"):
        p = export_dir / pattern
        if p.is_file():
            return p
    hits = glob.glob(str(export_dir / "**" / "conversations.json"), recursive=True)
    return Path(hits[0]) if hits else None


def _message_text(content) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                texts.append(str(block["text"]))
        joined = "\n".join(texts).strip()
        return joined or None
    return None


def load_claude(export_dir: str | Path) -> list[dict]:
    export_dir = Path(export_dir)
    index: dict[str, dict] = {}
    index_path = _find_index(export_dir)
    if index_path is not None:
        try:
            for entry in json.loads(index_path.read_text(encoding="utf-8")):
                if not isinstance(entry, dict):
                    continue  # tolerate malformed/non-object index entries
                uuid = str(entry.get("uuid") or "")
                if uuid:
                    index[uuid] = entry
        except (json.JSONDecodeError, TypeError):
            index = {}

    jsonl_files = sorted(glob.glob(str(export_dir / "**" / "*.jsonl"), recursive=True))
    if not jsonl_files:
        raise FileNotFoundError(f"No *.jsonl conversation files found under {export_dir}")

    conversations: dict[str, dict] = {}
    for path in jsonl_files:
        stem = os.path.splitext(os.path.basename(path))[0]
        conv_id = stem
        meta = index.get(conv_id) or {}
        turns = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue  # tolerate non-object records
                if obj.get("type") not in ("user", "assistant"):
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                text = _message_text(msg.get("content"))
                if not text:
                    continue
                ts = obj.get("timestamp")
                turns.append({
                    "role": "user" if obj.get("type") == "user" else "assistant",
                    "text": text,
                    "ts": float(ts) if isinstance(ts, (int, float)) else None,
                })
        if not turns:
            continue
        turns.sort(key=lambda t: t["ts"] if t["ts"] is not None else 0)
        conversations[conv_id] = {
            "id": conv_id,
            "title": meta.get("name") or meta.get("title") or f"conversation-{conv_id[:8]}",
            "created": meta.get("created_at"),
            "updated": meta.get("updated_at"),
            "source": "claude",
            "turns": turns,
        }
    if not conversations:
        raise ValueError(f"No parseable conversation turns found under {export_dir}")
    return list(conversations.values())

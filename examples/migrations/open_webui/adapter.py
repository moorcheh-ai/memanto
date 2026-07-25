"""Convert an Open WebUI chat export into an importable OKF bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


class ExportError(ValueError):
    """Raised when an Open WebUI export cannot be converted safely."""


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        stamp = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(stamp, tz=UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64]
    return slug or fallback


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def current_branch(history: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the root-to-leaf branch selected by Open WebUI's currentId."""
    raw_messages = history.get("messages")
    if not isinstance(raw_messages, dict):
        raise ExportError("chat history.messages must be an object")
    messages = {
        key: value for key, value in raw_messages.items() if isinstance(value, dict)
    }
    if not messages:
        return []

    current_id = history.get("currentId")
    if current_id not in messages:
        leaves = [
            (key, message)
            for key, message in messages.items()
            if not any(
                child in messages for child in message.get("childrenIds", []) or []
            )
        ]
        if not leaves:
            raise ExportError("chat history has no currentId or terminal message")
        current_id = max(
            leaves,
            key=lambda item: (item[1].get("timestamp") or 0, item[0]),
        )[0]

    branch: list[dict[str, Any]] = []
    seen: set[str] = set()
    message_id: str | None = str(current_id)
    while message_id:
        if message_id in seen:
            raise ExportError(f"cycle detected in message ancestry at {message_id}")
        seen.add(message_id)
        message = messages.get(message_id)
        if message is None:
            raise ExportError(f"missing parent message {message_id}")
        branch.append({"id": message_id, **message})
        parent_id = message.get("parentId")
        message_id = str(parent_id) if parent_id else None
    branch.reverse()
    return branch


def _transcript(messages: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for message in messages:
        role = str(message.get("role") or "unknown").strip().title()
        content = _content_text(message.get("content"))
        if not content:
            continue
        details = [f"message_id={message['id']}"]
        model = message.get("model")
        if model:
            details.append(f"model={model}")
        stamp = _timestamp(message.get("timestamp"))
        if stamp:
            details.append(f"timestamp={stamp}")
        sections.append(f"## {role}\n\n{content}\n\n_({' | '.join(details)})_")
    return "\n\n".join(sections)


def normalize_export(data: Any) -> list[dict[str, Any]]:
    """Validate current and legacy Open WebUI export envelopes."""
    if isinstance(data, dict) and isinstance(data.get("chats"), list):
        data = data["chats"]
    if not isinstance(data, list):
        raise ExportError(
            "export root must be a JSON array or an object with a chats array"
        )
    chats: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ExportError(f"chat {index} must be an object")
        chat = item.get("chat") if isinstance(item.get("chat"), dict) else item
        history = chat.get("history")
        if not isinstance(history, dict):
            raise ExportError(f"chat {index} has no history object")
        chats.append({"envelope": item, "chat": chat, "history": history})
    return chats


def convert_export(
    data: Any, output_dir: Path, source_name: str = "chat-export.json"
) -> dict[str, Any]:
    """Write a deterministic OKF bundle and return its manifest."""
    normalized = normalize_export(data)
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent)
    )
    try:
        memories_dir = staging / "memories" / "artifact"
        memories_dir.mkdir(parents=True)
        records: list[dict[str, Any]] = []
        used_names: set[str] = set()
        skipped_empty = 0

        for index, record in enumerate(normalized):
            envelope, chat = record["envelope"], record["chat"]
            messages = current_branch(record["history"])
            body = _transcript(messages)
            if not body:
                skipped_empty += 1
                continue
            title = str(
                chat.get("title") or envelope.get("title") or f"Chat {index + 1}"
            )
            chat_id = str(envelope.get("id") or chat.get("id") or f"chat-{index + 1}")
            stem = _slug(title, f"chat-{index + 1}")
            suffix = hashlib.sha256(chat_id.encode()).hexdigest()[:10]
            filename = f"{stem}-{suffix}.md"
            if filename in used_names:
                raise ExportError(f"duplicate output filename for chat {chat_id}")
            used_names.add(filename)

            meta = (
                envelope.get("meta") if isinstance(envelope.get("meta"), dict) else {}
            )
            tags = ["open-webui", "conversation"]
            tags.extend(str(tag) for tag in meta.get("tags", []) if tag)
            timestamp = _timestamp(envelope.get("created_at") or chat.get("created_at"))
            frontmatter: dict[str, Any] = {
                "type": "artifact",
                "title": title,
                "description": "Conversation migrated from an Open WebUI chat export.",
                "tags": sorted(set(tags)),
                "x_memanto": {
                    "type": "artifact",
                    "source": "open-webui",
                    "confidence": 1.0,
                },
                "source_chat_id": chat_id,
                "source_message_ids": [message["id"] for message in messages],
                "source_message_count": len(messages),
            }
            if timestamp:
                frontmatter["timestamp"] = timestamp
            models = sorted(
                {str(message["model"]) for message in messages if message.get("model")}
            )
            if models:
                frontmatter["source_models"] = models
            document = f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}\n---\n\n{body}\n"
            (memories_dir / filename).write_text(
                document, encoding="utf-8", newline="\n"
            )
            records.append(
                {
                    "chat_id": chat_id,
                    "file": f"memories/artifact/{filename}",
                    "messages": len(messages),
                }
            )

        (staging / "index.md").write_text(
            "---\ntype: index\ntitle: Open WebUI migration\n---\n\n"
            f"Migrated {len(records)} conversations from `{source_name}`.\n",
            encoding="utf-8",
            newline="\n",
        )
        manifest = {
            "format": "okf",
            "source": "open-webui",
            "source_file": source_name,
            "conversations": len(records),
            "messages": sum(record["messages"] for record in records),
            "skipped_empty": skipped_empty,
            "records": records,
        }
        (staging / "migration-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        staging.replace(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Open WebUI chat-export JSON file")
    parser.add_argument("output", type=Path, help="Destination OKF bundle directory")
    args = parser.parse_args()
    data = json.loads(args.export.read_text(encoding="utf-8"))
    manifest = convert_export(data, args.output, args.export.name)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

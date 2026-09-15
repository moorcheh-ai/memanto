"""Convert a persisted LlamaIndex Memory SQLite store into an OKF bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

TABLE = "llama_index_memory"
VALID_TYPES = {
    "artifact",
    "commitment",
    "decision",
    "event",
    "fact",
    "goal",
    "learning",
    "observation",
    "preference",
    "relationship",
    "instruction",
}
SECRET_PATTERNS = (
    (
        re.compile(r"(?i)\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
)
SECRET_KEY = re.compile(r"(?i)(?:api[_ -]?key|token|password|secret)")


def redact(value: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_data(value: Any) -> Any:
    """Redact nested metadata without breaking its JSON/YAML structure."""
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED_SECRET]"
                if SECRET_KEY.search(str(key))
                else redact_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value


def _text_from_message(data: dict[str, Any]) -> str:
    texts = [
        str(block.get("text", "")).strip()
        for block in data.get("blocks", [])
        if block.get("block_type") == "text"
    ]
    return redact("\n\n".join(text for text in texts if text))


def _memory_type(role: str, metadata: dict[str, Any], text: str) -> str:
    explicit = str(metadata.get("memory_type", "")).lower()
    if explicit in VALID_TYPES:
        return explicit
    lowered = text.lower()
    signals = (
        ("preference", ("i prefer", "favorite", "rather")),
        ("decision", ("decided", "we chose", "selected")),
        ("goal", ("goal is", "we aim", "plan to")),
        ("instruction", ("avoid ", "must not", "never ")),
        ("commitment", ("i will", "we will", "promise")),
    )
    for candidate, phrases in signals:
        if any(phrase in lowered for phrase in phrases):
            return candidate
    if role in {"tool", "function"}:
        return "artifact"
    if role in {"assistant", "model", "chatbot"}:
        return "observation"
    return "fact"


def _title(text: str, memory_type: str) -> str:
    first = text.splitlines()[0].strip().rstrip(".")
    if len(first) > 72:
        first = first[:69].rstrip() + "..."
    return first or f"LlamaIndex {memory_type}"


def _iso_timestamp(nanoseconds: int) -> str:
    dt = datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def load_rows(database: Path) -> list[dict[str, Any]]:
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({TABLE})")}
        required = {"id", "key", "timestamp", "role", "status", "data"}
        if not required.issubset(columns):
            raise ValueError(
                f"{TABLE} is missing columns: {sorted(required - columns)}"
            )
        return [
            dict(row)
            for row in connection.execute(
                f'SELECT id, "key", timestamp, role, status, data '
                f"FROM {TABLE} ORDER BY timestamp, id"
            )
        ]
    finally:
        connection.close()


def convert(database: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing bundle: {output}")
    rows = load_rows(database)
    output.mkdir(parents=True)
    memories_dir = output / "memories"
    memories_dir.mkdir()
    type_counts: dict[str, int] = {}
    session_counts: dict[str, int] = {}
    manifest_entries: list[dict[str, Any]] = []

    for order, row in enumerate(rows, 1):
        data = json.loads(row["data"])
        metadata = data.get("additional_kwargs") or {}
        text = _text_from_message(data)
        if not text:
            continue
        role = str(row["role"])
        session_id = str(row["key"])
        memory_type = _memory_type(role, metadata, text)
        explicit_type = str(metadata.get("memory_type", "")).lower()
        title = _title(text, memory_type)
        record_id = f"llamaindex-{row['id']:05d}"
        timestamp = _iso_timestamp(int(row["timestamp"]))
        safe_metadata = redact_data(metadata)
        frontmatter = {
            "type": memory_type,
            "title": title,
            "description": text.splitlines()[0],
            "resource": f"llamaindex://{session_id}/{row['id']}",
            "tags": ["llamaindex", f"session:{session_id}", f"role:{role}"],
            "timestamp": timestamp,
            "x_memanto": {
                "type": memory_type,
                "confidence": 1.0 if explicit_type in VALID_TYPES else 0.75,
                "source": "llamaindex",
                "provenance": "imported",
                "status": row["status"],
            },
            "x_llamaindex": {
                "message_id": row["id"],
                "session_id": session_id,
                "role": role,
                "status": row["status"],
                "order": order,
                "additional_kwargs": safe_metadata,
            },
        }
        body = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
            + "\n---\n\n"
            + text
            + "\n"
        )
        type_dir = memories_dir / memory_type
        type_dir.mkdir(exist_ok=True)
        relative_path = Path("memories") / memory_type / f"{record_id}.md"
        (output / relative_path).write_text(body, encoding="utf-8")
        digest = hashlib.sha256(body.encode()).hexdigest()
        manifest_entries.append(
            {
                "source_id": row["id"],
                "session_id": session_id,
                "okf_path": str(relative_path),
                "sha256": digest,
            }
        )
        type_counts[memory_type] = type_counts.get(memory_type, 0) + 1
        session_counts[session_id] = session_counts.get(session_id, 0) + 1

    index_frontmatter = yaml.safe_dump(
        {"type": "index", "title": "LlamaIndex memory migration"},
        sort_keys=False,
    ).strip()
    links = "\n".join(
        f"- [{entry['source_id']}]({entry['okf_path']})" for entry in manifest_entries
    )
    (output / "index.md").write_text(
        f"---\n{index_frontmatter}\n---\n\n# LlamaIndex memories\n\n{links}\n",
        encoding="utf-8",
    )
    manifest = {
        "format": "okf",
        "source": "llama-index-core Memory / SQLAlchemyChatStore",
        "source_database": database.name,
        "source_records": len(rows),
        "mapped_memories": len(manifest_entries),
        "skipped": len(rows) - len(manifest_entries),
        "type_counts": type_counts,
        "session_counts": session_counts,
        "entries": manifest_entries,
    }
    (output / "migration-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = convert(args.database, args.output)
    print(json.dumps({k: v for k, v in manifest.items() if k != "entries"}, indent=2))


if __name__ == "__main__":
    main()

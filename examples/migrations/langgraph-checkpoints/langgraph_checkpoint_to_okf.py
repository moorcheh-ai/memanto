"""Convert LangGraph SQLite checkpoints into an importable OKF bundle.

The adapter deliberately uses ``SqliteSaver.list`` instead of reading private
SQLite tables.  That keeps checkpoint deserialization (including LangChain
message objects) in LangGraph's supported serializer boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from langgraph.checkpoint.sqlite import SqliteSaver

_INTERNAL_CHANNELS = {
    "__interrupt__",
    "__pregel_tasks",
    "__return__",
    "__start__",
}
_TYPE_BY_CHANNEL_TOKEN = {
    "decision": "decision",
    "fact": "fact",
    "instruction": "instruction",
    "preference": "preference",
    "profile": "fact",
    "rule": "instruction",
}
_VALID_MEMORY_TYPES = {
    "decision",
    "event",
    "fact",
    "instruction",
    "observation",
    "preference",
}


@dataclass(frozen=True)
class CheckpointState:
    """Latest materialized state for one LangGraph thread."""

    thread_id: str
    checkpoint_id: str
    checkpoint_ns: str
    created_at: str
    channel_values: Mapping[str, Any]


@dataclass(frozen=True)
class OkfRecord:
    """One portable memory ready to render as an OKF markdown document."""

    record_id: str
    memory_type: str
    title: str
    content: str
    resource: str
    timestamp: str
    tags: tuple[str, ...]
    metadata: Mapping[str, Any]


def load_latest_checkpoints(
    database: str | Path,
    *,
    thread_ids: Sequence[str] | None = None,
) -> list[CheckpointState]:
    """Load the newest checkpoint for every requested thread.

    ``SqliteSaver.list`` returns newest-first checkpoint tuples.  The first
    tuple seen for a thread is therefore its current materialized state.
    """

    database_path = Path(database)
    if not database_path.is_file():
        raise FileNotFoundError(f"LangGraph checkpoint database not found: {database}")

    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(database_uri, uri=True, check_same_thread=False)
    saver = SqliteSaver(conn)
    try:
        tuples: Iterable[Any]
        if thread_ids:
            tuples = (
                item
                for thread_id in thread_ids
                for item in saver.list({"configurable": {"thread_id": thread_id}})
            )
        else:
            tuples = saver.list(None)

        latest: dict[tuple[str, str], CheckpointState] = {}
        for item in tuples:
            configurable = item.config.get("configurable", {})
            thread_id = str(configurable.get("thread_id") or "").strip()
            if not thread_id:
                continue
            checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
            key = (thread_id, checkpoint_ns)
            if key in latest:
                continue

            checkpoint = item.checkpoint
            checkpoint_id = str(
                configurable.get("checkpoint_id") or checkpoint.get("id") or "latest"
            )
            created_at = _timestamp(checkpoint.get("ts"))
            channel_values = checkpoint.get("channel_values") or {}
            if not isinstance(channel_values, Mapping):
                channel_values = {}
            latest[key] = CheckpointState(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                checkpoint_ns=checkpoint_ns,
                created_at=created_at,
                channel_values=channel_values,
            )

        return sorted(
            latest.values(),
            key=lambda state: (state.thread_id, state.checkpoint_ns),
        )
    finally:
        conn.close()


def extract_records(
    checkpoints: Sequence[CheckpointState],
    *,
    excluded_channels: Iterable[str] = (),
    channel_types: Mapping[str, str] | None = None,
) -> list[OkfRecord]:
    """Map materialized checkpoint channels to portable memory records."""

    excluded = _INTERNAL_CHANNELS | set(excluded_channels)
    overrides = dict(channel_types or {})
    records: list[OkfRecord] = []

    for state in checkpoints:
        for channel, raw_value in sorted(state.channel_values.items()):
            if channel in excluded or channel.startswith("branch:"):
                continue
            if channel == "messages":
                records.extend(_message_records(state, raw_value))
                continue

            memory_type = overrides.get(channel) or _infer_type(channel)
            for key, value in _iter_channel_items(raw_value):
                if value is None or value == "" or value == [] or value == {}:
                    continue
                title = _title_for(channel, key, value)
                content = _content_for(channel, key, value)
                records.append(
                    _record(
                        state,
                        channel=channel,
                        key=key,
                        memory_type=memory_type,
                        title=title,
                        content=content,
                        metadata={"channel": channel, "key": key},
                    )
                )

    deduped = {record.record_id: record for record in records}
    return sorted(
        deduped.values(),
        key=lambda record: (record.memory_type, record.title, record.record_id),
    )


def write_okf_bundle(records: Sequence[OkfRecord], output: str | Path) -> Path:
    """Write records as one-file-per-memory OKF markdown."""

    output_path = Path(output)
    memories_dir = output_path / "memories"
    if output_path.exists() and any(output_path.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty: {output_path}. "
            "Choose a new directory so existing artifacts are never overwritten."
        )
    memories_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        "---",
        "type: index",
        "title: LangGraph checkpoint migration",
        "---",
        "",
        "# LangGraph checkpoint migration",
        "",
        f"Generated {len(records)} portable memories.",
        "",
    ]
    type_counts: dict[str, int] = {}
    for record in records:
        type_counts[record.memory_type] = type_counts.get(record.memory_type, 0) + 1
        filename = f"{_slug(record.title)}-{record.record_id[:10]}.md"
        relative = Path("memories") / filename
        (output_path / relative).write_text(_render_record(record), encoding="utf-8")
        index_lines.append(f"- [{record.title}]({relative.as_posix()})")

    (output_path / "index.md").write_text(
        "\n".join(index_lines).rstrip() + "\n",
        encoding="utf-8",
    )
    manifest = {
        "format": "okf",
        "source": "langgraph-sqlite-checkpoints",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "per_type": dict(sorted(type_counts.items())),
    }
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def convert_database(
    database: str | Path,
    output: str | Path,
    *,
    thread_ids: Sequence[str] | None = None,
    excluded_channels: Iterable[str] = (),
    channel_types: Mapping[str, str] | None = None,
) -> tuple[Path, list[CheckpointState], list[OkfRecord]]:
    """Run the complete checkpoint -> records -> OKF conversion."""

    checkpoints = load_latest_checkpoints(database, thread_ids=thread_ids)
    records = extract_records(
        checkpoints,
        excluded_channels=excluded_channels,
        channel_types=channel_types,
    )
    return write_okf_bundle(records, output), checkpoints, records


def _message_records(state: CheckpointState, raw_value: Any) -> list[OkfRecord]:
    if isinstance(raw_value, (str, bytes, Mapping)) or not isinstance(
        raw_value, Sequence
    ):
        values = [raw_value]
    else:
        values = list(raw_value)

    records: list[OkfRecord] = []
    for index, message in enumerate(values):
        role, content, message_id, metadata = _normalize_message(message, index)
        if not content:
            continue
        title = f"{role.title()} turn in {state.thread_id}"
        records.append(
            _record(
                state,
                channel="messages",
                key=message_id,
                memory_type="event",
                title=title,
                content=content,
                metadata={
                    "channel": "messages",
                    "message_role": role,
                    "message_id": message_id,
                    **metadata,
                },
                extra_tags=(f"role:{role}",),
            )
        )
    return records


def _normalize_message(
    message: Any, index: int
) -> tuple[str, str, str, dict[str, Any]]:
    if isinstance(message, Mapping):
        role = str(
            message.get("role")
            or message.get("type")
            or message.get("name")
            or "message"
        )
        content = _stringify(message.get("content", ""))
        message_id = str(message.get("id") or index)
        metadata = message.get("additional_kwargs") or {}
    else:
        role = str(
            getattr(message, "type", None)
            or getattr(message, "role", None)
            or message.__class__.__name__
        )
        content = _stringify(getattr(message, "content", message))
        message_id = str(getattr(message, "id", None) or index)
        metadata = getattr(message, "additional_kwargs", {}) or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return role.lower(), content.strip(), message_id, dict(metadata)


def _iter_channel_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            yield str(key), item
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            yield str(index), item
    else:
        yield "value", value


def _infer_type(channel: str) -> str:
    lowered = channel.lower()
    for token, memory_type in _TYPE_BY_CHANNEL_TOKEN.items():
        if token in lowered:
            return memory_type
    return "observation"


def _record(
    state: CheckpointState,
    *,
    channel: str,
    key: str,
    memory_type: str,
    title: str,
    content: str,
    metadata: Mapping[str, Any],
    extra_tags: Sequence[str] = (),
) -> OkfRecord:
    if memory_type not in _VALID_MEMORY_TYPES:
        raise ValueError(
            f"Unsupported Memanto memory type {memory_type!r} for channel {channel!r}"
        )
    identity = "\0".join(
        (
            state.thread_id,
            state.checkpoint_ns,
            state.checkpoint_id,
            channel,
            key,
            content,
        )
    )
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    namespace = state.checkpoint_ns or "root"
    resource = (
        f"langgraph://{_url_part(state.thread_id)}/{_url_part(namespace)}"
        f"/{_url_part(state.checkpoint_id)}#{_url_part(channel)}/{_url_part(key)}"
    )
    tags = (
        "langgraph",
        "checkpoint",
        f"thread:{state.thread_id}",
        f"channel:{channel}",
        *extra_tags,
    )
    return OkfRecord(
        record_id=record_id,
        memory_type=memory_type,
        title=title,
        content=content,
        resource=resource,
        timestamp=state.created_at,
        tags=tuple(dict.fromkeys(tags)),
        metadata={
            "thread_id": state.thread_id,
            "checkpoint_id": state.checkpoint_id,
            "checkpoint_ns": state.checkpoint_ns,
            **metadata,
        },
    )


def _title_for(channel: str, key: str, value: Any) -> str:
    label = key.replace("_", " ").strip().title()
    channel_label = channel.replace("_", " ").strip().title()
    if key == "value":
        return channel_label
    if isinstance(value, Mapping):
        for candidate in ("title", "name", "decision", "fact", "content"):
            if value.get(candidate):
                return str(value[candidate]).strip()[:100]
    return f"{channel_label}: {label}"


def _content_for(channel: str, key: str, value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return "\n".join(
            f"- **{str(item_key).replace('_', ' ').title()}:** {_stringify(item_value)}"
            for item_key, item_value in sorted(
                value.items(), key=lambda pair: str(pair[0])
            )
        )
    return f"{key.replace('_', ' ').title()}: {_stringify(value)}"


def _render_record(record: OkfRecord) -> str:
    frontmatter = {
        "type": record.memory_type,
        "title": record.title,
        "description": f"Imported from {record.metadata['channel']} in a LangGraph checkpoint.",
        "resource": record.resource,
        "tags": list(record.tags),
        "timestamp": record.timestamp,
        "x_memanto": {
            "type": record.memory_type,
            "confidence": 1.0,
            "source": "tool",
            "provenance": "imported",
            "langgraph": dict(record.metadata),
        },
    }
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    return f"---\n{yaml_text}\n---\n\n{record.content.rstrip()}\n"


def _timestamp(value: Any) -> str:
    if value:
        return str(value)
    return datetime.now(timezone.utc).isoformat()


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "memory"


def _url_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._~-]+", "-", value).strip("-") or "root"

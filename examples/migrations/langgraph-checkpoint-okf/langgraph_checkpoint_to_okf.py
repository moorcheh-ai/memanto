"""Convert LangGraph SQLite checkpoints into an OKF bundle.

This adapter reads a real ``langgraph-checkpoint-sqlite`` database through
LangGraph's own ``SqliteSaver`` serializer, extracts durable memory channels,
and writes a Memanto-compatible Open Knowledge Format bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver


VALID_MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}

CHANNEL_TYPE_HINTS = {
    "preferences": "preference",
    "preference": "preference",
    "facts": "fact",
    "fact": "fact",
    "decisions": "decision",
    "decision": "decision",
    "goals": "goal",
    "goal": "goal",
    "commitments": "commitment",
    "commitment": "commitment",
    "instructions": "instruction",
    "instruction": "instruction",
    "relationships": "relationship",
    "relationship": "relationship",
    "observations": "observation",
    "observation": "observation",
    "memories": "observation",
    "memory": "observation",
}


@dataclass
class MemoryRecord:
    title: str
    content: str
    memory_type: str
    timestamp: str
    confidence: float
    tags: list[str]
    resource: str
    source_path: str
    source_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or fallback


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def unique_filename(record: MemoryRecord, used: set[str]) -> str:
    base = slugify(record.title, short_hash(record.content))
    filename = f"{base}.md"
    if filename in used:
        suffix = short_hash(record.source_id or f"{record.source_path}\n{record.content}")
        stem = base[: max(1, 79 - len(suffix))]
        filename = f"{stem}-{suffix}.md"
        counter = 2
        while filename in used:
            filename = f"{stem}-{suffix}-{counter}.md"
            counter += 1
    used.add(filename)
    return filename


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def infer_type(raw_type: Any, channel: str, content: str) -> str:
    candidate = clean_text(raw_type).lower().replace(" ", "_").replace("-", "_")
    if candidate in VALID_MEMORY_TYPES:
        return candidate

    prefix = content.split(":", 1)[0].strip().lower()
    if prefix in VALID_MEMORY_TYPES:
        return prefix

    channel_key = channel.lower().rstrip("s")
    return CHANNEL_TYPE_HINTS.get(channel.lower()) or CHANNEL_TYPE_HINTS.get(
        channel_key, "observation"
    )


def title_from(content: str, fallback: str = "LangGraph memory") -> str:
    first_line = content.strip().splitlines()[0] if content.strip() else fallback
    if ":" in first_line and len(first_line.split(":", 1)[0]) < 24:
        first_line = first_line.split(":", 1)[1].strip()
    return first_line[:96].rstrip() or fallback


def list_checkpoints(db_path: Path, thread_id: str | None = None) -> list[Any]:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        config = None
        if thread_id:
            config = {"configurable": {"thread_id": thread_id}}
        return list(saver.list(config))
    finally:
        conn.close()


def is_memory_channel(channel: str) -> bool:
    lowered = channel.lower()
    return (
        lowered in CHANNEL_TYPE_HINTS
        or "mem" in lowered
        or lowered in {"facts", "decisions", "goals", "preferences"}
    )


def iter_memory_items(value: Any, path: str = "") -> Iterable[tuple[Any, str]]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_memory_items(item, f"{path}/{index}")
    elif isinstance(value, dict):
        content = (
            value.get("content")
            or value.get("memory")
            or value.get("text")
            or value.get("value")
        )
        if content:
            yield value, path or "/"
        else:
            for key, item in value.items():
                yield from iter_memory_items(item, f"{path}/{key}")
    elif isinstance(value, str) and value.strip():
        yield value, path or "/"


def coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def record_from_item(
    item: Any,
    *,
    channel: str,
    item_path: str,
    thread_id: str,
    checkpoint_id: str,
    checkpoint_ts: str,
) -> MemoryRecord | None:
    if isinstance(item, dict):
        content = clean_text(
            item.get("content")
            or item.get("memory")
            or item.get("text")
            or item.get("value")
        )
        if not content:
            return None
        raw_type = item.get("type")
        title = clean_text(item.get("title")) or title_from(content)
        tags = coerce_tags(item.get("tags"))
        timestamp = clean_text(item.get("timestamp") or item.get("created_at"))
        confidence_raw = item.get("confidence", 0.82)
        source_id = clean_text(item.get("id")) or None
        extra = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "content",
                "memory",
                "text",
                "value",
                "type",
                "title",
                "tags",
                "timestamp",
                "created_at",
                "confidence",
                "id",
            }
        }
    else:
        content = clean_text(item)
        if not content:
            return None
        raw_type = None
        title = title_from(content)
        tags = []
        timestamp = ""
        confidence_raw = 0.78
        source_id = None
        extra = {}

    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.82
    confidence = max(0.0, min(1.0, confidence))

    memory_type = infer_type(raw_type, channel, content)
    timestamp = timestamp or checkpoint_ts

    base_tags = [
        "langgraph",
        f"thread:{thread_id}",
        f"channel:{channel}",
    ]
    if extra.get("source_session"):
        base_tags.append(f"session:{extra['source_session']}")

    resource = (
        f"langgraph://thread/{thread_id}/checkpoint/{checkpoint_id}"
        f"/channel/{channel}{item_path}"
    )

    return MemoryRecord(
        title=title,
        content=content,
        memory_type=memory_type,
        timestamp=timestamp,
        confidence=confidence,
        tags=list(dict.fromkeys(base_tags + tags)),
        resource=resource,
        source_path=f"{checkpoint_id}:{channel}{item_path}",
        source_id=source_id,
        extra=extra,
    )


def extract_records(db_path: Path, thread_id: str | None = None) -> list[MemoryRecord]:
    checkpoints = list_checkpoints(db_path, thread_id)
    records: list[MemoryRecord] = []
    seen: set[str] = set()

    for item in reversed(checkpoints):
        configurable = item.config.get("configurable", {})
        current_thread = configurable.get("thread_id", "unknown-thread")
        checkpoint_id = configurable.get("checkpoint_id", item.checkpoint.get("id", ""))
        checkpoint_ts = item.checkpoint.get("ts", "")
        channel_values = item.checkpoint.get("channel_values", {})

        for channel, value in channel_values.items():
            if not is_memory_channel(channel):
                continue
            for raw_item, item_path in iter_memory_items(value):
                record = record_from_item(
                    raw_item,
                    channel=channel,
                    item_path=item_path,
                    thread_id=current_thread,
                    checkpoint_id=checkpoint_id,
                    checkpoint_ts=checkpoint_ts,
                )
                if record is None:
                    continue
                key = record.source_id or short_hash(
                    f"{record.memory_type}\n{record.title}\n{record.content}"
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)

    return records


def frontmatter(record: MemoryRecord) -> str:
    data: dict[str, Any] = {
        "type": record.memory_type,
        "title": record.title,
        "description": record.content.splitlines()[0][:180],
        "tags": record.tags,
        "timestamp": record.timestamp,
        "resource": record.resource,
        "x_memanto": {
            "confidence": record.confidence,
            "provenance": "imported_langgraph_checkpoint",
            "source": "langgraph-checkpoint",
            "type": record.memory_type,
        },
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False).strip()


def render_memory(record: MemoryRecord) -> str:
    supporting = {
        "source_path": record.source_path,
        "source_id": record.source_id,
        "langgraph_extra": record.extra,
    }
    footer = json.dumps(supporting, indent=2, sort_keys=True, ensure_ascii=True)
    return (
        "---\n"
        f"{frontmatter(record)}\n"
        "---\n\n"
        f"{record.content}\n\n"
        "## LangGraph provenance\n\n"
        f"Source path: `{record.source_path}`\n\n"
        "```json\n"
        f"{footer}\n"
        "```\n"
    )


def render_index(records: list[MemoryRecord]) -> str:
    per_type: dict[str, int] = {}
    for record in records:
        per_type[record.memory_type] = per_type.get(record.memory_type, 0) + 1
    lines = [
        "# LangGraph checkpoint OKF bundle",
        "",
        "This bundle was generated from a real LangGraph SQLite checkpoint.",
        "",
        "## Counts",
        "",
    ]
    for memory_type, count in sorted(per_type.items()):
        lines.append(f"- {memory_type}: {count}")
    lines.extend(["", "## Sections", "", "- [Memories](memories/index.md)"])
    lines.append("- [Session log](sessions/founder-os-agent.md)")
    lines.append("- [Metrics](metrics/overview.md)")
    return "\n".join(lines) + "\n"


def render_sessions(records: list[MemoryRecord]) -> str:
    lines = [
        "# LangGraph Session Log",
        "",
        "Each row links an OKF memory back to its checkpoint and channel path.",
        "",
        "| Type | Title | Source path |",
        "| --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            f"| {record.memory_type} | {record.title} | `{record.source_path}` |"
        )
    return "\n".join(lines) + "\n"


def render_metrics(records: list[MemoryRecord]) -> str:
    per_type: dict[str, int] = {}
    for record in records:
        per_type[record.memory_type] = per_type.get(record.memory_type, 0) + 1
    lines = [
        "# Migration Metrics",
        "",
        f"- Source memories mapped: {len(records)}",
        f"- OKF memory files written: {len(records)}",
        "- Source: langgraph-checkpoint-sqlite",
        "- Adapter: langgraph_checkpoint_to_okf.py",
        "",
        "## Type Breakdown",
        "",
    ]
    for memory_type, count in sorted(per_type.items()):
        lines.append(f"- {memory_type}: {count}")
    return "\n".join(lines) + "\n"


def validate_output_path(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    if resolved == Path.cwd().resolve():
        raise RuntimeError("Refusing to write an OKF bundle into the current directory")
    if resolved == resolved.parent:
        raise RuntimeError("Refusing to write an OKF bundle into a filesystem root")
    if resolved.exists() and not resolved.is_dir():
        raise RuntimeError(f"Output path exists and is not a directory: {resolved}")
    return resolved


def is_generated_okf_bundle(output: Path) -> bool:
    index = output / "index.md"
    if not output.is_dir() or not index.exists():
        return False
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return False
    return "generated from a real LangGraph SQLite checkpoint" in text


def write_okf_bundle_contents(records: list[MemoryRecord], output: Path) -> None:
    (output / "memories").mkdir(parents=True)
    (output / "sessions").mkdir()
    (output / "metrics").mkdir()

    output.joinpath("index.md").write_text(render_index(records), encoding="utf-8")
    output.joinpath("sessions", "founder-os-agent.md").write_text(
        render_sessions(records), encoding="utf-8"
    )
    output.joinpath("metrics", "overview.md").write_text(
        render_metrics(records), encoding="utf-8"
    )

    memory_index = ["# Memories", ""]
    for memory_type in sorted({record.memory_type for record in records}):
        type_records = [r for r in records if r.memory_type == memory_type]
        type_dir = output / "memories" / memory_type
        type_dir.mkdir(parents=True, exist_ok=True)
        memory_index.append(f"- [{memory_type}]({memory_type}/index.md)")

        type_index = [f"# {memory_type.title()} Memories", ""]
        used_filenames: set[str] = set()
        for record in type_records:
            filename = unique_filename(record, used_filenames)
            type_dir.joinpath(filename).write_text(
                render_memory(record), encoding="utf-8"
            )
            type_index.append(f"- [{record.title}]({filename})")
        type_dir.joinpath("index.md").write_text(
            "\n".join(type_index) + "\n", encoding="utf-8"
        )

    output.joinpath("memories", "index.md").write_text(
        "\n".join(memory_index) + "\n", encoding="utf-8"
    )


def write_okf_bundle(records: list[MemoryRecord], output: Path, *, overwrite: bool = False) -> None:
    target = validate_output_path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp-{short_hash(str(target))}")
    if temp.exists():
        if temp.is_dir():
            shutil.rmtree(temp)
        else:
            temp.unlink()

    try:
        write_okf_bundle_contents(records, temp)
        if target.exists():
            if not overwrite:
                raise RuntimeError(
                    f"Output bundle already exists; pass overwrite=True to replace it: {target}"
                )
            if not is_generated_okf_bundle(target):
                raise RuntimeError(
                    f"Refusing to overwrite non-generated OKF bundle: {target}"
                )
            shutil.rmtree(target)
        temp.rename(target)
    except Exception:
        if temp.exists():
            shutil.rmtree(temp)
        raise


def convert(
    db_path: Path,
    output: Path,
    thread_id: str | None = None,
    *,
    overwrite: bool = False,
) -> list[MemoryRecord]:
    records = extract_records(db_path, thread_id=thread_id)
    if not records:
        raise RuntimeError(f"No memory records found in {db_path}")
    write_okf_bundle(records, output, overwrite=overwrite)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("sample_output/okf_bundle"))
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    records = convert(
        args.db_path,
        args.output,
        thread_id=args.thread_id,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "source": str(args.db_path),
                "output": str(args.output),
                "mapped_memories": len(records),
                "types": sorted({record.memory_type for record in records}),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()

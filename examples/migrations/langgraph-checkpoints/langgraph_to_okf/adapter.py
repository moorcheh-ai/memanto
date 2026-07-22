"""Convert the latest state of each LangGraph thread to an OKF bundle.

The adapter uses LangGraph's public ``SqliteSaver.list`` API for checkpoint
deserialization. A SQLite backup is opened instead of the source database so
the migration never writes to, locks, or partially reads a live source file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

# LangGraph recommends strict MessagePack deserialization when a checkpoint
# database might not be fully trusted. This must be set before importing the
# SQLite checkpointer and its serializer.
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from langchain_core.messages import BaseMessage  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402


@dataclass
class MigrationSummary:
    source: str
    output: str
    threads: int = 0
    checkpoints: int = 0
    memories: int = 0
    memories_by_type: dict[str, int] = field(default_factory=dict)
    thread_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ThreadRef:
    thread_id: str
    checkpoint_ns: str


def _slug(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or fallback)[:72]


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return {
            "role": value.type,
            "content": _message_text(value),
            "id": value.id,
            "name": getattr(value, "name", None),
            "additional_kwargs": value.additional_kwargs,
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return repr(value)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(json.dumps(_jsonable(item), ensure_ascii=False))
        return "\n".join(part.strip() for part in parts if part).strip()
    return json.dumps(_jsonable(content), ensure_ascii=False)


def _snapshot_database(source: Path, destination: Path) -> None:
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as source_conn:
        with closing(sqlite3.connect(destination)) as destination_conn:
            source_conn.backup(destination_conn)


def _discover_threads(conn: sqlite3.Connection) -> list[_ThreadRef]:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkpoints'"
    ).fetchone()
    if table is None:
        raise ValueError("The SQLite file has no LangGraph checkpoints table")

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(checkpoints)").fetchall()
    }
    required = {"thread_id", "checkpoint_ns"}
    if not required.issubset(columns):
        raise ValueError(
            "Unsupported LangGraph checkpoint schema: missing "
            + ", ".join(sorted(required - columns))
        )

    rows = conn.execute(
        "SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints "
        "ORDER BY thread_id, checkpoint_ns"
    ).fetchall()
    return [
        _ThreadRef(str(thread_id), str(namespace or ""))
        for thread_id, namespace in rows
    ]


def _memory(
    *,
    title: str,
    body: str,
    memory_type: str,
    tags: list[str],
    timestamp: str,
    resource: str,
    source_channel: str,
) -> dict[str, Any]:
    return {
        "type": memory_type,
        "title": title,
        "body": body.strip(),
        "tags": list(dict.fromkeys(tags)),
        "timestamp": timestamp,
        "resource": resource,
        "source_channel": source_channel,
        "x_memanto": {
            "type": memory_type,
            "source": "langgraph",
            "confidence": 1.0,
            "provenance": "imported",
        },
    }


def _semantic_type(channel: str, key: str = "") -> str:
    hint = f"{channel} {key}".lower()
    if any(token in hint for token in ("preference", "preferred", "style", "format")):
        return "preference"
    if "decision" in hint:
        return "decision"
    if "goal" in hint:
        return "goal"
    if "commitment" in hint or "task" in hint:
        return "commitment"
    return "fact"


def _state_to_memories(
    ref: _ThreadRef,
    state: dict[str, Any],
    timestamp: str,
    checkpoint_id: str,
) -> list[dict[str, Any]]:
    tags = [f"langgraph-thread:{ref.thread_id}"]
    if ref.checkpoint_ns:
        tags.append(f"langgraph-namespace:{ref.checkpoint_ns}")
    base_resource = "langgraph://{}/{}/{}".format(
        quote(ref.thread_id, safe=""),
        quote(ref.checkpoint_ns or "root", safe=""),
        quote(checkpoint_id, safe=""),
    )
    memories: list[dict[str, Any]] = []

    messages = state.get("messages")
    if isinstance(messages, list) and messages:
        transcript_lines: list[str] = []
        for message in messages:
            if isinstance(message, BaseMessage):
                text = _message_text(message)
                if text:
                    transcript_lines.append(f"**{message.type}:** {text}")
            else:
                transcript_lines.append(
                    "**message:** " + json.dumps(_jsonable(message), ensure_ascii=False)
                )
        if transcript_lines:
            memories.append(
                _memory(
                    title=f"LangGraph transcript: {ref.thread_id}",
                    body="\n\n".join(transcript_lines),
                    memory_type="artifact",
                    tags=tags + ["langgraph-channel:messages"],
                    timestamp=timestamp,
                    resource=f"{base_resource}#messages",
                    source_channel="messages",
                )
            )

    for channel, value in state.items():
        if (
            channel == "messages"
            or channel.startswith("__")
            or _is_empty(value)
        ):
            continue

        if isinstance(value, dict):
            for key, item in value.items():
                if _is_empty(item):
                    continue
                rendered = (
                    item
                    if isinstance(item, str)
                    else json.dumps(_jsonable(item), ensure_ascii=False, indent=2)
                )
                memories.append(
                    _memory(
                        title=f"{str(key).replace('_', ' ').title()}: {rendered[:72]}",
                        body=f"{str(key).replace('_', ' ').title()}: {rendered}",
                        memory_type=_semantic_type(channel, str(key)),
                        tags=tags + [f"langgraph-channel:{channel}"],
                        timestamp=timestamp,
                        resource=f"{base_resource}#{_slug(channel)}-{_slug(str(key))}",
                        source_channel=channel,
                    )
                )
            continue

        if isinstance(value, list):
            for index, item in enumerate(value):
                if _is_empty(item):
                    continue
                rendered = (
                    item
                    if isinstance(item, str)
                    else json.dumps(_jsonable(item), ensure_ascii=False, indent=2)
                )
                memories.append(
                    _memory(
                        title=f"{channel.replace('_', ' ').title()}: {rendered[:72]}",
                        body=rendered,
                        memory_type=_semantic_type(channel),
                        tags=tags + [f"langgraph-channel:{channel}"],
                        timestamp=timestamp,
                        resource=f"{base_resource}#{_slug(channel)}-{index + 1}",
                        source_channel=channel,
                    )
                )
            continue

        rendered = (
            value
            if isinstance(value, str)
            else json.dumps(_jsonable(value), ensure_ascii=False, indent=2)
        )
        memories.append(
            _memory(
                title=f"{channel.replace('_', ' ').title()}: {rendered[:72]}",
                body=rendered,
                memory_type=_semantic_type(channel),
                tags=tags + [f"langgraph-channel:{channel}"],
                timestamp=timestamp,
                resource=f"{base_resource}#{_slug(channel)}",
                source_channel=channel,
            )
        )

    return memories


def _extract_memories(
    conn: sqlite3.Connection, refs: Iterable[_ThreadRef]
) -> tuple[list[dict[str, Any]], int]:
    saver = SqliteSaver(conn)
    memories: list[dict[str, Any]] = []
    checkpoint_count = int(
        conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    )

    for ref in refs:
        config = {
            "configurable": {
                "thread_id": ref.thread_id,
                "checkpoint_ns": ref.checkpoint_ns,
            }
        }
        checkpoints = saver.list(config, limit=1)
        try:
            latest = next(checkpoints, None)
        finally:
            checkpoints.close()
        if latest is None:
            continue
        checkpoint = latest.checkpoint
        state = checkpoint.get("channel_values") or {}
        if not isinstance(state, dict):
            continue
        timestamp = str(checkpoint.get("ts") or datetime.now(timezone.utc).isoformat())
        checkpoint_id = str(
            latest.config.get("configurable", {}).get("checkpoint_id")
            or checkpoint.get("id")
            or "latest"
        )
        memories.extend(_state_to_memories(ref, state, timestamp, checkpoint_id))

    return memories, checkpoint_count


def _write_markdown(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(
        frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n", encoding="utf-8")


def _write_bundle(
    output_dir: Path,
    memories: list[dict[str, Any]],
    summary: MigrationSummary,
    *,
    overwrite: bool,
) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output bundle already exists: {output_dir}. "
                "Choose a new directory or enable overwrite explicitly."
            )
        if output_dir.is_file():
            raise ValueError(
                f"Output path is a file, expected a directory: {output_dir}"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    used_paths: set[Path] = set()
    index_rows: list[tuple[str, Path, str]] = []
    for index, memory in enumerate(memories, 1):
        memory_type = memory["type"]
        stem = _slug(memory["title"])
        relative = Path("memories") / memory_type / f"{stem}.md"
        if relative in used_paths:
            relative = Path("memories") / memory_type / f"{stem}-{index}.md"
        used_paths.add(relative)

        frontmatter = {
            "type": memory_type,
            "title": memory["title"],
            "tags": memory["tags"],
            "timestamp": memory["timestamp"],
            "resource": memory["resource"],
            "source_channel": memory["source_channel"],
            "x_memanto": memory["x_memanto"],
        }
        _write_markdown(output_dir / relative, frontmatter, memory["body"])
        index_rows.append((memory_type, relative, memory["title"]))

    root_lines = [
        "# LangGraph checkpoint migration",
        "",
        "This bundle was generated from real LangGraph SQLite checkpoints.",
        "The original database was opened through a read-only snapshot.",
        "",
        f"- Threads: {summary.threads}",
        f"- Source checkpoints: {summary.checkpoints}",
        f"- Portable memories: {summary.memories}",
        "",
        "## Memories",
    ]
    for memory_type, relative, title in index_rows:
        root_lines.append(f"- [{title}]({relative.as_posix()}) ({memory_type})")
    _write_markdown(
        output_dir / "index.md",
        {"type": "index", "title": "LangGraph checkpoint migration"},
        "\n".join(root_lines),
    )

    metrics_lines = [
        "# Migration summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Threads | {summary.threads} |",
        f"| Source checkpoints | {summary.checkpoints} |",
        f"| Portable memories | {summary.memories} |",
        "",
        "## Memory types",
    ]
    for memory_type, count in sorted(summary.memories_by_type.items()):
        metrics_lines.append(f"- {memory_type}: {count}")
    _write_markdown(
        output_dir / "metrics" / "migration-summary.md",
        {"type": "index", "title": "Migration summary"},
        "\n".join(metrics_lines),
    )
    portable_summary = summary.to_dict()
    portable_summary["source"] = Path(summary.source).name
    portable_summary["output"] = Path(summary.output).name
    (output_dir / "migration-summary.json").write_text(
        json.dumps(portable_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def convert_checkpoint_database(
    source: str | Path, output: str | Path, *, overwrite: bool = False
) -> MigrationSummary:
    """Convert a LangGraph SQLite checkpoint database into an OKF bundle."""
    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Checkpoint database not found: {source_path}")
    if source_path == output_path or source_path.is_relative_to(output_path):
        raise ValueError("The output directory cannot contain the source database")

    with tempfile.TemporaryDirectory(prefix="langgraph-okf-") as temp_dir:
        snapshot = Path(temp_dir) / "checkpoint-snapshot.sqlite"
        _snapshot_database(source_path, snapshot)
        with closing(sqlite3.connect(snapshot, check_same_thread=False)) as conn:
            refs = _discover_threads(conn)
            memories, checkpoint_count = _extract_memories(conn, refs)

    counts: dict[str, int] = {}
    for memory in memories:
        counts[memory["type"]] = counts.get(memory["type"], 0) + 1
    summary = MigrationSummary(
        source=str(source_path),
        output=str(output_path),
        threads=len({ref.thread_id for ref in refs}),
        checkpoints=checkpoint_count,
        memories=len(memories),
        memories_by_type=counts,
        thread_ids=sorted({ref.thread_id for ref in refs}),
    )
    _write_bundle(output_path, memories, summary, overwrite=overwrite)
    return summary

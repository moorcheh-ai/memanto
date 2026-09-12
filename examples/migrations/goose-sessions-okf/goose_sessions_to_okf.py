"""Convert local goose session history into an OKF bundle.

This example intentionally stays offline and dependency-free. It accepts:

* a goose Desktop/CLI JSON session export,
* a directory containing JSON or legacy JSONL session files, or
* a read-only copy of the current ``sessions.db`` SQLite database.

The output is a small Open Knowledge Format bundle: markdown files with YAML
frontmatter plus Memanto's ``x_memanto`` provenance extension.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "preference",
    "relationship",
    "context",
    "event",
    "observation",
    "constraint",
    "commitment",
    "error",
}

GENERATED_MARKER = ".goose-okf-generated"
MAX_TITLE_CHARS = 96
MAX_BODY_CHARS = 2500
SESSION_FILE_SUFFIXES = {".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}


@dataclass
class GooseMessage:
    role: str
    content: str
    timestamp: str | None = None
    kind: str | None = None


@dataclass
class GooseSession:
    session_id: str
    description: str
    source_ref: str
    working_dir: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    model: str | None = None
    provider: str | None = None
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[GooseMessage] | None = None

    @property
    def safe_description(self) -> str:
        return self.description or self.session_id


@dataclass
class OkfMemory:
    memory_type: str
    title: str
    body: str
    source_ref: str
    tags: list[str]
    timestamp: str | None = None
    confidence: float = 0.76
    description: str | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or fallback


def truncate(value: str, limit: int) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def normalize_timestamp(value: Any) -> str | None:
    if value in (None, "", 0) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


TOKEN_RE = re.compile(
    r"(?i)\b(?:sk|ghp|gho|ghu|github_pat|xoxb|xoxp|api[_-]?key|token)"
    r"[A-Za-z0-9_\-:=.]{8,}"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
API_KEY_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*"
    r"\s*[:=]\s*)(['\"]?)[^'\"\s,;]{8,}\2"
)
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
UNIX_HOME_RE = re.compile(r"(?<!\w)/(?:Users|home)/[^/\s]+")
WINDOWS_HOME_RE = re.compile(
    r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\AppData\\(?:Local|Roaming))?"
)
TURN_CONTEXT_RE = re.compile(r"<turn-context>.*?</turn-context>", re.DOTALL)
WORKING_DIRECTORY_FIELD_RE = re.compile(r"(?im)(Working directory:\s*`)[^`]+(`)")


def redact_text(text: str) -> str:
    text = WORKING_DIRECTORY_FIELD_RE.sub(r"\1[REDACTED_PATH]\2", text)
    text = BEARER_TOKEN_RE.sub("Bearer [REDACTED_TOKEN]", text)
    text = API_KEY_ASSIGNMENT_RE.sub(r"\1[REDACTED_TOKEN]", text)
    text = AWS_ACCESS_KEY_RE.sub("[REDACTED_TOKEN]", text)
    text = TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = WINDOWS_HOME_RE.sub("[REDACTED_HOME]", text)
    text = UNIX_HOME_RE.sub("[REDACTED_HOME]", text)
    return text


def compact_text(value: Any) -> str:
    """Return readable text from the common content shapes in agent logs."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [compact_text(item) for item in value]
        return "\n".join(part for part in parts if part.strip())
    if isinstance(value, dict):
        for key in ("text", "content", "message", "body", "value", "result"):
            if key in value:
                text = compact_text(value.get(key))
                if text.strip():
                    return text
        if "arguments" in value:
            return compact_text(value["arguments"])
        if "error" in value:
            return compact_text(value["error"])
    return ""


def normalize_message(raw: Any) -> GooseMessage | None:
    if isinstance(raw, str):
        content = raw.strip()
        return GooseMessage(role="unknown", content=content) if content else None
    if not isinstance(raw, dict):
        return None

    role = str(
        raw.get("role")
        or raw.get("author")
        or raw.get("speaker")
        or raw.get("type")
        or "unknown"
    ).lower()
    content = compact_text(
        raw.get("content")
        or raw.get("text")
        or raw.get("message")
        or raw.get("body")
        or raw.get("value")
        or raw.get("result")
    ).strip()
    if not content and raw.get("tool_call"):
        content = compact_text(raw["tool_call"]).strip()
    content = TURN_CONTEXT_RE.sub("", content).strip()
    if not content:
        return None

    kind = raw.get("kind") or raw.get("type")
    timestamp = normalize_timestamp(
        raw.get("created_at")
        or raw.get("createdAt")
        or raw.get("created_timestamp")
        or raw.get("timestamp")
        or raw.get("time")
    )
    return GooseMessage(role=role, content=content, timestamp=timestamp, kind=kind)


def _messages_from_container(raw: dict[str, Any]) -> list[GooseMessage]:
    for key in (
        "messages",
        "conversation",
        "history",
        "transcript",
        "interactions",
        "entries",
    ):
        candidate = raw.get(key)
        if isinstance(candidate, list):
            messages: list[GooseMessage] = []
            for item in candidate:
                if isinstance(item, GooseMessage):
                    messages.append(item)
                    continue
                if (msg := normalize_message(item)) is not None:
                    messages.append(msg)
            return messages
    return []


def normalize_session(raw: dict[str, Any], source_ref: str) -> GooseSession | None:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    model_config = parse_jsonish(raw.get("model_config_json"))
    if not isinstance(model_config, dict):
        model_config = {}
    session_id = str(
        raw.get("id")
        or raw.get("session_id")
        or raw.get("sessionId")
        or raw.get("session")
        or Path(source_ref).stem
    )
    description = str(
        raw.get("description")
        or raw.get("title")
        or raw.get("name")
        or metadata.get("name")
        or raw.get("summary")
        or session_id
    )
    messages = _messages_from_container(raw)
    if not messages and not description:
        return None

    return GooseSession(
        session_id=session_id,
        description=description,
        source_ref=source_ref,
        working_dir=raw.get("working_dir")
        or raw.get("workingDir")
        or raw.get("cwd")
        or raw.get("directory")
        or metadata.get("working_dir"),
        created_at=normalize_timestamp(raw.get("created_at") or raw.get("createdAt")),
        updated_at=normalize_timestamp(raw.get("updated_at") or raw.get("updatedAt")),
        model=raw.get("model")
        or raw.get("provider_model")
        or metadata.get("model")
        or model_config.get("model_name"),
        provider=raw.get("provider")
        or raw.get("provider_name")
        or metadata.get("provider"),
        total_tokens=int(raw.get("total_tokens") or 0),
        input_tokens=int(raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        messages=messages,
    )


def iter_json_payloads(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        payloads: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                payloads.append(value)
        return payloads

    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if isinstance(value.get("sessions"), list):
            return [item for item in value["sessions"] if isinstance(item, dict)]
        return [value]
    return []


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]


def rows_as_dicts(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(row) for row in rows]


def parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def read_sessions_db(path: Path) -> list[GooseSession]:
    """Best-effort read of goose's SQLite session store.

    The public docs guarantee a ``sessions`` table with id, description,
    working_dir, and created_at. Message storage can evolve, so this reader
    supports both JSON-in-session columns and separate message tables.
    """
    sessions: dict[str, dict[str, Any]] = {}
    messages_by_session: dict[str, list[GooseMessage]] = {}

    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = sqlite_tables(conn)

        if "sessions" in tables:
            for row in rows_as_dicts(conn, "sessions"):
                sid = str(row.get("id") or row.get("session_id") or "")
                if not sid:
                    continue
                sessions[sid] = {
                    "id": sid,
                    "description": row.get("description") or row.get("name") or sid,
                    "working_dir": row.get("working_dir") or row.get("cwd"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "model": row.get("model"),
                    "model_config_json": row.get("model_config_json"),
                    "provider_name": row.get("provider_name"),
                    "total_tokens": row.get("total_tokens") or 0,
                    "input_tokens": row.get("input_tokens") or 0,
                    "output_tokens": row.get("output_tokens") or 0,
                    "messages": [],
                }
                for key in ("messages", "conversation", "history", "transcript"):
                    parsed = parse_jsonish(row.get(key))
                    if isinstance(parsed, list):
                        sessions[sid]["messages"] = parsed
                        break

        for table in tables:
            columns = set(table_columns(conn, table))
            content_column = next(
                (column for column in ("content", "content_json") if column in columns),
                None,
            )
            if "role" not in columns or content_column is None:
                continue
            sid_column = next(
                (
                    col
                    for col in ("session_id", "sessionId", "conversation_id")
                    if col in columns
                ),
                None,
            )
            order_column = next(
                (
                    col
                    for col in (
                        "created_at",
                        "created_timestamp",
                        "timestamp",
                        "time",
                        "idx",
                        "id",
                    )
                    if col in columns
                ),
                None,
            )
            order_sql = f" ORDER BY {order_column}" if order_column else ""
            for row in conn.execute(f"SELECT * FROM {table}{order_sql}").fetchall():
                item = dict(row)
                if content_column == "content_json":
                    item["content"] = parse_jsonish(item.get("content_json"))
                sid = str(item.get(sid_column) or item.get("session") or "unknown")
                if sid not in sessions:
                    sessions[sid] = {
                        "id": sid,
                        "description": sid,
                        "messages": [],
                    }
                parsed = normalize_message(item)
                if parsed is not None:
                    messages_by_session.setdefault(sid, []).append(parsed)

    normalized: list[GooseSession] = []
    for sid, payload in sessions.items():
        if messages_by_session.get(sid):
            payload["messages"] = messages_by_session[sid]
        session = normalize_session(payload, f"{path.name}#{sid}")
        if session is not None:
            normalized.append(session)
    return normalized


def read_goose_sources(path: Path) -> list[GooseSession]:
    if path.is_file() and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return read_sessions_db(path)

    files = (
        [path]
        if path.is_file()
        else sorted(
            item
            for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in SESSION_FILE_SUFFIXES
        )
    )

    sessions: list[GooseSession] = []
    for file_path in files:
        if file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            sessions.extend(read_sessions_db(file_path))
            continue
        for idx, payload in enumerate(iter_json_payloads(file_path), start=1):
            source_ref = f"{file_path.name}#{idx}"
            session = normalize_session(payload, source_ref)
            if session is not None:
                sessions.append(session)
    return sessions


def classify_message(message: GooseMessage) -> str | None:
    text = message.content.lower()
    if any(word in text for word in ("error", "failed", "traceback", "exception")):
        return "error"
    if re.search(r"\b(decision|decided|we chose|chose|instead of)\b", text):
        return "decision"
    if re.search(
        r"\b(always|prefer|preference|avoid|never|do not|don't|remember)\b", text
    ):
        return "preference" if message.role == "user" else "instruction"
    if re.search(
        r"\b(done|fixed|implemented|added|created|updated|tests? pass|verified)\b",
        text,
    ):
        return "fact"
    return None


def first_user_message(session: GooseSession) -> str:
    for msg in session.messages or []:
        if msg.role in {"user", "human"}:
            return truncate(msg.content, 280)
    return ""


def last_assistant_message(session: GooseSession) -> str:
    for msg in reversed(session.messages or []):
        if msg.role in {"assistant", "ai", "model"}:
            return truncate(msg.content, 360)
    return ""


def make_session_memory(session: GooseSession) -> OkfMemory:
    body_parts = [
        f"Session id: `{session.session_id}`",
        f"Description: {session.safe_description}",
    ]
    if session.working_dir:
        body_parts.append(f"Working directory: `{session.working_dir}`")
    if session.model:
        body_parts.append(f"Model: `{session.model}`")
    if session.provider:
        body_parts.append(f"Provider: `{session.provider}`")
    if session.total_tokens:
        body_parts.append(f"Recorded tokens: {session.total_tokens}")
    first = first_user_message(session)
    if first:
        body_parts.append(f"First user prompt: {first}")
    last = last_assistant_message(session)
    if last:
        body_parts.append(f"Latest assistant summary: {last}")

    return OkfMemory(
        memory_type="event",
        title=truncate(f"Goose session: {session.safe_description}", MAX_TITLE_CHARS),
        body="\n\n".join(body_parts),
        source_ref=session.source_ref,
        tags=["goose", "session"],
        timestamp=session.created_at or session.updated_at,
        confidence=0.82,
        description="Session-level memory extracted from goose local history.",
    )


def message_memory(
    session: GooseSession, message: GooseMessage, index: int
) -> OkfMemory | None:
    memory_type = classify_message(message)
    if memory_type is None:
        return None
    role = message.role or "unknown"
    title = truncate(
        f"{memory_type.title()} from {session.safe_description}", MAX_TITLE_CHARS
    )
    body = truncate(message.content, MAX_BODY_CHARS)
    return OkfMemory(
        memory_type=memory_type,
        title=title,
        body=body,
        source_ref=f"{session.source_ref}/message-{index}",
        tags=["goose", "transcript", role, memory_type],
        timestamp=message.timestamp or session.created_at,
        confidence=0.74,
        description=f"Extracted from a goose {role} message.",
    )


def extract_memories(
    sessions: list[GooseSession],
    *,
    redact: bool = True,
    max_memories_per_session: int = 12,
) -> list[OkfMemory]:
    memories: list[OkfMemory] = []
    for session in sessions:
        session_memory = make_session_memory(session)
        memories.append(session_memory)

        per_session = 0
        for idx, message in enumerate(session.messages or [], start=1):
            if per_session >= max_memories_per_session:
                break
            memory = message_memory(session, message, idx)
            if memory is None:
                continue
            memories.append(memory)
            per_session += 1

    if redact:
        for memory in memories:
            memory.title = redact_text(memory.title)
            memory.body = redact_text(memory.body)
            memory.description = redact_text(memory.description or "")
            memory.source_ref = redact_text(memory.source_ref)
    return memories


def yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(yaml_scalar(value) for value in values) + "]"


def render_memory(memory: OkfMemory) -> str:
    timestamp = memory.timestamp or utc_timestamp()
    lines = [
        "---",
        f"type: {yaml_scalar(memory.memory_type)}",
        f"title: {yaml_scalar(memory.title)}",
        f"description: {yaml_scalar(memory.description or '')}",
        f"resource: {yaml_scalar(memory.source_ref)}",
        f"tags: {yaml_list(memory.tags)}",
        f"timestamp: {yaml_scalar(timestamp)}",
        "x_memanto:",
        f"  source: {yaml_scalar('goose-sessions')}",
        f"  source_ref: {yaml_scalar(memory.source_ref)}",
        f"  confidence: {memory.confidence:.2f}",
        "  provenance: imported",
        "---",
        "",
        memory.body.strip(),
        "",
    ]
    return "\n".join(lines)


def prepare_output_dir(path: Path, *, force: bool) -> None:
    if path.exists():
        marker = path / GENERATED_MARKER
        if not marker.exists() and not force:
            raise FileExistsError(
                f"{path} already exists. Pass --force to replace it, or choose a new --out."
            )
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / GENERATED_MARKER).write_text(
        "generated by goose_sessions_to_okf.py\n", encoding="utf-8"
    )


def write_bundle(
    memories: list[OkfMemory],
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    prepare_output_dir(output_dir, force=force)
    memories_dir = output_dir / "memories"
    metrics_dir = output_dir / "metrics"
    memories_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    type_counts: Counter[str] = Counter()
    used_names: Counter[str] = Counter()
    for memory in memories:
        type_counts[memory.memory_type] += 1
        type_dir = memories_dir / memory.memory_type
        type_dir.mkdir(parents=True, exist_ok=True)
        base = slugify(memory.title)
        used_names[base] += 1
        suffix = f"-{used_names[base]}" if used_names[base] > 1 else ""
        (type_dir / f"{base}{suffix}.md").write_text(
            render_memory(memory),
            encoding="utf-8",
        )

    (output_dir / "index.md").write_text(
        "# Goose sessions OKF bundle\n\n"
        "This bundle was generated from local goose session history.\n\n"
        "## Sections\n\n"
        "- [Memories](memories/index.md)\n"
        "- [Metrics](metrics/overview.md)\n",
        encoding="utf-8",
    )
    (memories_dir / "index.md").write_text(
        "# Memories\n\n"
        + "\n".join(
            f"- {memory_type}: {count}"
            for memory_type, count in sorted(type_counts.items())
        )
        + "\n",
        encoding="utf-8",
    )
    (metrics_dir / "overview.md").write_text(
        "# Migration metrics\n\n"
        f"- Total memories: {len(memories)}\n"
        + "\n".join(
            f"- {memory_type}: {count}"
            for memory_type, count in sorted(type_counts.items())
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "output_path": str(output_dir),
        "mapped_memories": len(memories),
        "type_counts": dict(sorted(type_counts.items())),
    }


def build_summary(
    *,
    source: Path,
    sessions: list[GooseSession],
    memories: list[OkfMemory],
    bundle_result: dict[str, Any],
    redact: bool,
) -> dict[str, Any]:
    source_label = redact_text(str(source)) if redact else str(source)
    output_label = (
        redact_text(str(bundle_result["output_path"]))
        if redact
        else str(bundle_result["output_path"])
    )
    summary = {
        "provider": "goose",
        "source": source_label,
        "source_sessions": len(sessions),
        "source_messages": sum(len(session.messages or []) for session in sessions),
        "source_tokens": sum(session.total_tokens for session in sessions),
        "source_input_tokens": sum(session.input_tokens for session in sessions),
        "source_output_tokens": sum(session.output_tokens for session in sessions),
        "mapped_memories": len(memories),
        "type_counts": bundle_result["type_counts"],
        "output_path": output_label,
        "generated_at": utc_timestamp(),
    }
    return summary


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def convert_source(
    source: Path,
    output_dir: Path,
    *,
    summary_path: Path | None = None,
    redact: bool = True,
    force: bool = False,
    max_memories_per_session: int = 12,
    session_ids: set[str] | None = None,
) -> dict[str, Any]:
    sessions = read_goose_sources(source)
    if session_ids:
        sessions = [
            session for session in sessions if session.session_id in session_ids
        ]
    if not sessions:
        raise ValueError(f"No goose sessions found in {source}")
    memories = extract_memories(
        sessions,
        redact=redact,
        max_memories_per_session=max_memories_per_session,
    )
    bundle_result = write_bundle(memories, output_dir, force=force)
    summary = build_summary(
        source=source,
        sessions=sessions,
        memories=memories,
        bundle_result=bundle_result,
        redact=redact,
    )
    if summary_path is not None:
        write_summary(summary_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert goose session JSON/JSONL/SQLite history to OKF markdown."
    )
    parser.add_argument(
        "source", type=Path, help="goose export file, sessions.db, or directory"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="output OKF bundle directory"
    )
    parser.add_argument(
        "--summary", type=Path, help="write a migration summary JSON file"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing generated output directory",
    )
    parser.add_argument(
        "--no-redact", action="store_true", help="disable default privacy redaction"
    )
    parser.add_argument(
        "--max-memories-per-session",
        type=int,
        default=12,
        help="cap extracted transcript memories per session",
    )
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="include one session id; repeat to include several",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = convert_source(
        args.source,
        args.out,
        summary_path=args.summary,
        redact=not args.no_redact,
        force=args.force,
        max_memories_per_session=args.max_memories_per_session,
        session_ids=set(args.session_ids) if args.session_ids else None,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

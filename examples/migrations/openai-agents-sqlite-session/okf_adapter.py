#!/usr/bin/env python3
"""
OpenAI Agents SDK ``SQLiteSession`` -> OKF 0.2 bundle.

The OpenAI Agents SDK persists conversation history as raw OpenAI *Responses*
items in a SQLite file (``agent_messages.message_data`` holds one JSON item per
row). Memanto can import an OKF bundle, but nothing bridges the two. This
adapter is that bridge.

Design rules
------------
* **Stdlib only.** ``sqlite3`` + ``json`` + ``argparse``; no SDK import needed to
  read a database the SDK produced, so the adapter runs anywhere the file does.
* **Read-only, identifier-safe.** The database is opened with SQLite's
  ``mode=ro`` URI. Table names are validated against a strict identifier pattern
  *and* introspected from ``sqlite_master`` / ``PRAGMA table_info`` before use —
  never interpolated blind.
* **No semantic guessing.** Item text is carried across verbatim. The adapter
  assigns a Memanto memory type only for tool records, where the source shape is
  unambiguous (``artifact`` — "tool outputs, files, reports"); user and assistant
  messages are left untyped so Memanto's own classifier decides.
* **Nothing is silently stringified.** Item kinds that are not conversation
  content (reasoning traces, hosted-tool calls, images, ...) are skipped and
  counted by reason in the report rather than dumped into a memory body.
* **Deterministic.** Output is a pure function of the source rows: no wall clock,
  no randomness, sorted iteration. Re-running over an unchanged database yields
  byte-identical files. Run metadata that *is* time-dependent lives only in the
  ``--report`` JSON, never in the bundle.

Usage
-----
    python okf_adapter.py --db ./sessions.db --list-sessions
    python okf_adapter.py --db ./sessions.db --session my-session --out ./okf
    python okf_adapter.py --db ./sessions.db --session my-session --out ./okf \
        --report ./report.json --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ADAPTER_NAME = "openai-agents-sqlite-session-to-okf"
ADAPTER_VERSION = "1.0.0"
OKF_VERSION = "0.2"

#: Written into every generated ``index.md``. ``--force`` refuses to overwrite a
#: directory whose ``index.md`` does not carry this marker, so the adapter can
#: never clobber a bundle (or any other folder) it did not produce.
GENERATOR_MARKER = f"<!-- generated-by: {ADAPTER_NAME} -->"

#: Memanto's ``x_memanto.source`` for every document produced here.
SOURCE_LABEL = "openai-agents-sqlite-session"

#: OKF ``generated.by`` (spec §7 actor identity). The permitted forms are
#: ``<producer>/<version>``, ``human:<id>`` and ``process:<id>``; this adapter is
#: a tool, so it uses the producer form and carries its own version. The source
#: role (user / assistant / tool) is *not* an actor identity — it is preserved in
#: ``tags``, the body's provenance line and ``x_memanto.provenance`` instead.
GENERATED_BY = f"{ADAPTER_NAME}/{ADAPTER_VERSION}"

#: SQL identifiers we are willing to interpolate, before introspection confirms
#: the table actually exists.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SLUG_RE = re.compile(r"[^a-z0-9]+")

#: Responses content blocks that carry plain text.
_TEXT_BLOCK_TYPES = ("input_text", "output_text", "text", "summary_text")

#: Message roles the adapter turns into memories.
_MESSAGE_ROLES = ("user", "assistant", "system", "developer")

#: Confidence per record kind. Verbatim human statements and deterministic tool
#: results score higher than model prose, which can contain model error.
_CONFIDENCE = {
    "user-message": 0.9,
    "assistant-message": 0.75,
    "system-message": 0.9,
    "tool-call": 0.9,
    "tool-output": 0.9,
}

#: Memanto ``provenance`` recorded for round-tripping. (Memanto's own importer
#: always stamps imported rows as ``imported``; this preserves the origin.)
_PROVENANCE = {
    "user-message": "explicit_statement",
    "assistant-message": "observed",
    "system-message": "explicit_statement",
    "tool-call": "observed",
    "tool-output": "observed",
}

_TITLE_CHARS = 80
_DESCRIPTION_CHARS = 200

#: Opening words of the caveat added when a concept has no usable timestamp. Used
#: to find and replace a stale caveat when a merged record's timestamp changes.
_TIMESTAMP_NOTE_PREFIX = "No usable source timestamp"


class AdapterError(Exception):
    """Raised for user-facing failures (bad path, unknown table, no session)."""


# ---------------------------------------------------------------------------
# Source reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRow:
    """One raw ``agent_messages`` row."""

    row_id: int
    session_id: str
    created_at: str
    payload: Any  # decoded JSON, or None when the row is not decodable
    decode_error: str | None = None


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    item_count: int
    created_at: str | None
    updated_at: str | None


def _validate_identifier(name: str, label: str) -> str:
    if not _IDENTIFIER_RE.match(name or ""):
        raise AdapterError(
            f"Invalid {label} {name!r}: expected a plain SQL identifier "
            "([A-Za-z_][A-Za-z0-9_]*)."
        )
    return name


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the SDK's database read-only so a migration can never mutate it."""
    if not db_path.is_file():
        raise AdapterError(f"SQLite database not found: {db_path}")
    # ``as_uri()`` percent-encodes the path, so a filename containing '?' or '#'
    # cannot terminate the path early and turn into a query or fragment.
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


@contextmanager
def consistent_snapshot(db_path: Path) -> Iterator[Path]:
    """Yield a private, transactionally consistent copy of the source database.

    ``SQLiteSession`` runs in WAL mode, which makes the raw ``.db`` file a bad
    basis for both reading and evidence:

    * committed rows can live only in the ``-wal`` sidecar, so two *different*
      logical states can share one main-file hash; and
    * separate connections each get their own read snapshot, so a concurrent
      writer can change the data between the rows read and the metadata read.

    SQLite's backup API copies the database through a single read transaction on
    the source — WAL content included — into a standalone file with no sidecars.
    Reading rows and metadata from that copy, and hashing that same copy, makes
    the report describe exactly one logical state.

    The source stays read-only, and the temporary copy is always removed.
    """
    source = connect_readonly(db_path)
    tmp_dir = Path(tempfile.mkdtemp(prefix="okf-adapter-snapshot-"))
    try:
        snapshot_path = tmp_dir / "source-snapshot.sqlite3"
        destination = sqlite3.connect(str(snapshot_path))
        try:
            source.backup(destination)
        finally:
            destination.close()
        yield snapshot_path
    finally:
        source.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Column names of *table* (the table name is already validated)."""
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _optional_column(present: set[str], column: str) -> str:
    """Select *column* when the table has it, otherwise a NULL of the same name.

    ``SQLiteSession`` always creates ``created_at``/``updated_at``, but a custom
    ``sessions_table`` may legitimately carry only ``session_id``. Selecting a
    NULL alias keeps the result shape stable instead of raising OperationalError.
    """
    return f'"{column}"' if column in present else f"NULL AS {column}"


def _require_table(
    conn: sqlite3.Connection, table: str, columns: tuple[str, ...]
) -> None:
    """Confirm *table* exists and exposes *columns* (schema introspection)."""
    found = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if not found:
        available = sorted(
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        )
        raise AdapterError(
            f"Table {table!r} not found in the database. Tables present: "
            f"{', '.join(available) or '(none)'}"
        )
    present = _table_columns(conn, table)
    missing = [col for col in columns if col not in present]
    if missing:
        raise AdapterError(
            f"Table {table!r} is missing expected column(s): {', '.join(missing)}. "
            "This does not look like an OpenAI Agents SDK session table."
        )


def list_sessions(
    db_path: Path,
    *,
    sessions_table: str = "agent_sessions",
    messages_table: str = "agent_messages",
) -> list[SessionInfo]:
    """List sessions in the database, newest activity first."""
    _validate_identifier(sessions_table, "sessions table")
    _validate_identifier(messages_table, "messages table")

    conn = connect_readonly(db_path)
    try:
        _require_table(conn, messages_table, ("id", "session_id", "message_data"))
        counts: dict[str, int] = {
            str(sid): int(n)
            for sid, n in conn.execute(
                f'SELECT session_id, COUNT(*) FROM "{messages_table}" GROUP BY session_id'  # noqa: S608 - identifier validated + introspected above
            )
        }

        rows: list[SessionInfo] = []
        try:
            _require_table(conn, sessions_table, ("session_id",))
        except AdapterError:
            # A messages table with no sessions table is still readable.
            return [SessionInfo(sid, counts[sid], None, None) for sid in sorted(counts)]

        present = _table_columns(conn, sessions_table)
        created_col = _optional_column(present, "created_at")
        updated_col = _optional_column(present, "updated_at")
        for sid, created_at, updated_at in conn.execute(
            f'SELECT session_id, {created_col}, {updated_col} FROM "{sessions_table}"'  # noqa: S608 - identifiers validated + introspected above
        ):
            rows.append(
                SessionInfo(
                    session_id=str(sid),
                    item_count=counts.get(str(sid), 0),
                    created_at=_as_text(created_at),
                    updated_at=_as_text(updated_at),
                )
            )
        # Sessions written directly into the messages table without a metadata
        # row still deserve to be listed.
        known = {row.session_id for row in rows}
        rows.extend(
            SessionInfo(sid, counts[sid], None, None)
            for sid in sorted(counts)
            if sid not in known
        )
        rows.sort(key=lambda s: (s.updated_at or "", s.session_id), reverse=True)
        return rows
    finally:
        conn.close()


def read_rows(
    db_path: Path,
    session_id: str,
    *,
    messages_table: str = "agent_messages",
    source_label: str | None = None,
) -> list[SourceRow]:
    """Read one session's items in insertion order (``ORDER BY id``).

    ``source_label`` names the database in error messages; ``migrate`` passes the
    user's own path so a temporary read snapshot never leaks into output.
    """
    _validate_identifier(messages_table, "messages table")

    conn = connect_readonly(db_path)
    try:
        _require_table(
            conn, messages_table, ("id", "session_id", "message_data", "created_at")
        )
        cursor = conn.execute(
            f'SELECT id, session_id, message_data, created_at FROM "{messages_table}" '  # noqa: S608 - identifier validated + introspected above
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = [_decode_row(raw) for raw in cursor.fetchall()]
    finally:
        conn.close()

    if not rows:
        raise AdapterError(
            f"No items found for session {session_id!r} in {source_label or db_path}. "
            "Run with --list-sessions to see what is available."
        )
    return rows


def _decode_row(raw: tuple[Any, Any, Any, Any]) -> SourceRow:
    row_id, session_id, message_data, created_at = raw
    payload: Any = None
    error: str | None = None
    if not isinstance(message_data, str):
        error = f"message_data is {type(message_data).__name__}, expected TEXT"
    else:
        try:
            payload = json.loads(message_data)
        except (json.JSONDecodeError, ValueError) as exc:
            error = f"invalid JSON ({exc.__class__.__name__})"
    return SourceRow(
        row_id=int(row_id),
        session_id=str(session_id),
        created_at=_as_text(created_at) or "",
        payload=payload,
        decode_error=error,
    )


def read_session_meta(
    db_path: Path,
    session_id: str,
    *,
    sessions_table: str = "agent_sessions",
) -> dict[str, str | None]:
    """Read the ``agent_sessions`` metadata row, when the table exists."""
    _validate_identifier(sessions_table, "sessions table")
    conn = connect_readonly(db_path)
    try:
        try:
            _require_table(conn, sessions_table, ("session_id",))
        except AdapterError:
            return {"created_at": None, "updated_at": None}
        present = _table_columns(conn, sessions_table)
        created_col = _optional_column(present, "created_at")
        updated_col = _optional_column(present, "updated_at")
        row = conn.execute(
            f'SELECT {created_col}, {updated_col} FROM "{sessions_table}" '  # noqa: S608 - identifiers validated + introspected above
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"created_at": None, "updated_at": None}
    return {"created_at": _as_text(row[0]), "updated_at": _as_text(row[1])}


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


@dataclass
class Record:
    """One OKF document to be written."""

    kind: str  # user-message | assistant-message | system-message | tool-call | tool-output
    role: str | None
    turn: int
    row_ids: list[int]
    timestamp: str | None  # ISO 8601 UTC, or None when the source had none
    title: str
    body: str
    tags: list[str]
    memanto_type: str | None
    notes: list[str] = field(default_factory=list)

    @property
    def primary_row_id(self) -> int:
        return self.row_ids[0]


@dataclass
class Skipped:
    row_id: int
    reason: str
    detail: str


@dataclass
class Transformed:
    records: list[Record]
    skipped: list[Skipped]
    session_id: str


def _iso(created_at: str | None) -> str | None:
    """Normalise a SQLite ``CURRENT_TIMESTAMP`` value to ISO 8601 UTC.

    The SDK stores ``YYYY-MM-DD HH:MM:SS`` in UTC. Anything already ISO-shaped is
    given an explicit UTC offset. Blank or unparseable input returns ``None``:
    OKF's ``timestamp`` and ``generated.at`` must be ISO 8601 (spec §5.2), so the
    field is dropped rather than emitted malformed — and no timestamp is invented
    to fill the gap. Callers surface the omission as a note and in the report.
    """
    text = (created_at or "").strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _slugify(text: str, fallback: str = "item") -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:60].rstrip("-") or fallback


def _shorten(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: max(1, limit - 3)].rstrip() + "..."


def _extract_text(content: Any) -> tuple[str, list[str]]:
    """Pull plain text out of a Responses ``content`` field.

    Returns ``(text, unsupported_block_types)``. Non-text blocks (images, files,
    refusals, ...) are reported, never stringified into the memory body.
    """
    if isinstance(content, str):
        return content.strip(), []
    if not isinstance(content, list):
        # A bare dict / int / None is not conversation text — refuse to guess.
        return "", [type(content).__name__] if content is not None else []

    parts: list[str] = []
    unsupported: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            unsupported.append(type(block).__name__)
            continue
        block_type = str(block.get("type") or "")
        if block_type in _TEXT_BLOCK_TYPES and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block_type:
            unsupported.append(block_type)
        else:
            unsupported.append("untyped-block")
    return "\n\n".join(p.strip() for p in parts if p.strip()).strip(), unsupported


def _item_kind(payload: dict[str, Any]) -> str:
    """Classify a Responses item by shape.

    Plain conversation items may carry only ``role``; SDK-generated items always
    carry ``type``.
    """
    item_type = str(payload.get("type") or "").strip()
    role = str(payload.get("role") or "").strip()
    if item_type in ("", "message") and role in _MESSAGE_ROLES:
        # ``developer`` is a system-level role in the Responses API.
        return {"user": "user-message", "assistant": "assistant-message"}.get(
            role, "system-message"
        )
    return item_type or "unknown"


def _render_payload(raw: Any) -> tuple[str, str]:
    """Render a tool payload for the body. Never a Python ``repr``.

    Returns ``(text, language)`` where *language* is the fence tag: ``json`` only
    when the payload really is JSON, ``text`` when a tool returned a plain string
    that must be preserved verbatim.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return "", ""
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text, "text"
        return json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False), "json"
    if raw is None:
        return "", ""
    return json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False), "json"


def _fence(payload: str, language: str) -> str:
    """Fence a payload, widening the fence if the payload contains backticks."""
    fence = "```"
    while fence in payload:
        fence += "`"
    return f"{fence}{language}\n{payload}\n{fence}"


def transform(rows: list[SourceRow], session_id: str) -> Transformed:
    """Map raw session rows onto OKF documents.

    ``function_call`` and its matching ``function_call_output`` collapse into one
    tool record: separately, a call id without its result is not a memory.
    """
    records: list[Record] = []
    skipped: list[Skipped] = []
    pending_calls: dict[str, Record] = {}
    turn = 0

    for row in rows:
        if row.decode_error is not None:
            skipped.append(Skipped(row.row_id, "undecodable_row", row.decode_error))
            continue
        if not isinstance(row.payload, dict):
            skipped.append(
                Skipped(
                    row.row_id,
                    "unexpected_item_shape",
                    f"top-level item is {type(row.payload).__name__}, expected object",
                )
            )
            continue

        payload: dict[str, Any] = row.payload
        kind = _item_kind(payload)
        timestamp = _iso(row.created_at)
        timestamp_note = _timestamp_note(row.created_at, timestamp)

        if kind in ("user-message", "assistant-message", "system-message"):
            if kind == "user-message":
                turn += 1
            record = _build_message_record(row, payload, kind, turn, timestamp)
            if record is None:
                skipped.append(
                    Skipped(row.row_id, "no_text_content", f"{kind} carried no text")
                )
                continue
            _note_timestamp(record, timestamp_note)
            records.append(record)

        elif kind == "function_call":
            record = _build_tool_call_record(row, payload, turn, timestamp)
            if record is None:
                skipped.append(
                    Skipped(
                        row.row_id,
                        "malformed_tool_call",
                        "function_call without a name",
                    )
                )
                continue
            _note_timestamp(record, timestamp_note)
            records.append(record)
            call_id = str(payload.get("call_id") or "")
            if call_id:
                pending_calls[call_id] = record

        elif kind == "function_call_output":
            call_id = str(payload.get("call_id") or "")
            target = pending_calls.pop(call_id, None)
            if target is not None:
                _attach_tool_output(target, row, payload, timestamp)
            else:
                # An orphan result still carries information; keep it rather than
                # dropping data, but label it honestly.
                orphan = _build_orphan_output_record(row, payload, turn, timestamp)
                _note_timestamp(orphan, timestamp_note)
                records.append(orphan)

        elif kind == "reasoning":
            skipped.append(
                Skipped(
                    row.row_id,
                    "reasoning_trace",
                    "model reasoning item — internal scratchpad, not a memory",
                )
            )
        else:
            skipped.append(Skipped(row.row_id, "unsupported_item_type", kind))

    return Transformed(records=records, skipped=skipped, session_id=session_id)


def _timestamp_note(raw: str, normalised: str | None) -> str | None:
    """Explain a dropped timestamp so the loss is visible in the document."""
    if normalised is not None:
        return None
    if raw.strip():
        return (
            f"{_TIMESTAMP_NOTE_PREFIX}: `{raw.strip()}` is not ISO 8601, so no "
            "`timestamp` or `generated` block was recorded for this concept."
        )
    return f"{_TIMESTAMP_NOTE_PREFIX}: the source item did not record one."


def _note_timestamp(record: Record, note: str | None) -> None:
    """Replace any earlier timestamp caveat — a record carries at most one, and it
    must describe the timestamp the record actually ended up with."""
    record.notes = [n for n in record.notes if not n.startswith(_TIMESTAMP_NOTE_PREFIX)]
    if note:
        record.notes.append(note)


def _build_message_record(
    row: SourceRow,
    payload: dict[str, Any],
    kind: str,
    turn: int,
    timestamp: str | None,
) -> Record | None:
    text, unsupported = _extract_text(payload.get("content"))
    if not text:
        return None

    role = str(payload.get("role") or "").strip() or kind.split("-")[0]
    label = {"user-message": "User", "assistant-message": "Assistant"}.get(
        kind, role.capitalize()
    )
    notes: list[str] = []
    if unsupported:
        notes.append(
            "Non-text content blocks present in the source item and not carried "
            f"across: {', '.join(sorted(set(unsupported)))}."
        )
    status = payload.get("status")
    if isinstance(status, str) and status and status != "completed":
        notes.append(f"Source item status: `{status}`.")

    body = "\n\n".join(
        [
            f"{label} message from turn {turn} of OpenAI Agents SDK session "
            f"`{row.session_id}`.",
            text,
        ]
    )
    return Record(
        kind=kind,
        role=role,
        turn=turn,
        row_ids=[row.row_id],
        timestamp=timestamp,
        title=f"{label} · turn {turn} · {_shorten(text, _TITLE_CHARS - 20)}",
        body=body,
        tags=_tags(row.session_id, kind, turn, role=role),
        memanto_type=None,  # left to Memanto's classifier
        notes=notes,
    )


def _build_tool_call_record(
    row: SourceRow,
    payload: dict[str, Any],
    turn: int,
    timestamp: str | None,
) -> Record | None:
    name = str(payload.get("name") or "").strip()
    if not name:
        return None

    arguments, arguments_lang = _render_payload(payload.get("arguments"))
    body_parts = [
        f"Tool `{name}` was called during turn {turn} of OpenAI Agents SDK session "
        f"`{row.session_id}`."
    ]
    if arguments:
        body_parts.append("**Arguments**\n\n" + _fence(arguments, arguments_lang))

    record = Record(
        kind="tool-call",
        role="assistant",
        turn=turn,
        row_ids=[row.row_id],
        timestamp=timestamp,
        title=f"Tool call · turn {turn} · {name}",
        body="\n\n".join(body_parts),
        tags=_tags(row.session_id, "tool-call", turn, tool=name),
        # Unambiguous: Memanto's "artifact" type is tool outputs / reports.
        memanto_type="artifact",
        notes=["Result item missing from the session — call recorded without output."],
    )
    call_id = str(payload.get("call_id") or "")
    if call_id:
        record.notes.insert(0, f"Tool call id `{call_id}`.")
    return record


def _attach_tool_output(
    record: Record, row: SourceRow, payload: dict[str, Any], timestamp: str | None
) -> None:
    """Fold a ``function_call_output`` into the record for its ``function_call``.

    The merged concept now ends with the result, so its ``generated.at`` must be
    the result row's timestamp — OKF §5.2 defines that field as the last
    meaningful content change. When the result row has no usable timestamp the
    record keeps none: the call's earlier timestamp would misdescribe content
    that grew after it.
    """
    result, language = _render_payload(payload.get("output"))
    if result:
        record.body += "\n\n**Result**\n\n" + _fence(result, language)
    else:
        record.body += "\n\n**Result** — the tool returned no output."
    record.row_ids.append(row.row_id)
    record.timestamp = timestamp
    _note_timestamp(record, _timestamp_note(row.created_at, timestamp))
    # Drop the "missing output" caveat now that the result arrived.
    record.notes = [n for n in record.notes if not n.startswith("Result item missing")]


def _build_orphan_output_record(
    row: SourceRow,
    payload: dict[str, Any],
    turn: int,
    timestamp: str | None,
) -> Record:
    call_id = str(payload.get("call_id") or "") or "unknown"
    result, language = _render_payload(payload.get("output"))
    body = (
        f"Tool result recorded during turn {turn} of OpenAI Agents SDK session "
        f"`{row.session_id}`. The matching call item is not present in this session."
    )
    if result:
        body += "\n\n**Result**\n\n" + _fence(result, language)
    return Record(
        kind="tool-output",
        role="tool",
        turn=turn,
        row_ids=[row.row_id],
        timestamp=timestamp,
        title=f"Tool result · turn {turn} · call {call_id}",
        body=body,
        tags=_tags(row.session_id, "tool-output", turn),
        memanto_type="artifact",
        notes=[f"Orphan result for call id `{call_id}` — no matching call item."],
    )


def _tags(
    session_id: str,
    kind: str,
    turn: int,
    *,
    role: str | None = None,
    tool: str | None = None,
) -> list[str]:
    tags = [
        "openai-agents",
        f"session:{session_id}",
        f"turn:{turn}",
        f"item:{kind}",
    ]
    if role:
        tags.append(f"role:{role}")
    if tool:
        tags.append(f"tool:{tool}")
    return tags


# ---------------------------------------------------------------------------
# OKF rendering
# ---------------------------------------------------------------------------


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    # A JSON string literal is also a valid YAML double-quoted scalar.
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_block(data: dict[str, Any], indent: int = 0) -> list[str]:
    """Emit a deterministic YAML mapping (scalars, string lists, nested maps)."""
    pad = " " * indent
    lines: list[str] = []
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            if not value:
                continue
            lines.append(f"{pad}{key}:")
            lines.extend(_yaml_block(value, indent + 2))
        elif isinstance(value, (list, tuple)):
            if not value:
                continue
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, dict):
                    inner = _yaml_block(item, indent + 4)
                    lines.append(f"{pad}  - {inner[0].strip()}")
                    lines.extend(inner[1:])
                else:
                    lines.append(f"{pad}  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")
    return lines


def render_document(record: Record, session_id: str, messages_table: str) -> str:
    """Render one OKF 0.2 document (YAML frontmatter + markdown body)."""
    resource = source_uri(session_id, messages_table, record.primary_row_id)
    body = record.body
    if record.notes:
        body += "\n\n" + "\n".join(f"> Note: {note}" for note in record.notes)
    body += "\n\n" + _provenance_block(record, session_id, messages_table)

    frontmatter: dict[str, Any] = {
        "type": f"openai-agents.{record.kind}",
        "title": record.title,
        "description": _shorten(record.body.splitlines()[0], _DESCRIPTION_CHARS),
        "resource": resource,
        "tags": record.tags,
        # Omitted when the source timestamp was absent or not ISO 8601 (§5.2).
        "timestamp": record.timestamp,
        "status": "stable",
        "generated": (
            {"by": GENERATED_BY, "at": record.timestamp} if record.timestamp else None
        ),
        "sources": [
            {
                "resource": source_uri(session_id, messages_table, row_id),
                "id": f"{messages_table}:{row_id}",
            }
            for row_id in record.row_ids
        ],
        "x_memanto": {
            # Same reasoning as source_uri: encode the session id so a ':' in it
            # cannot make this colon-delimited id ambiguous.
            "id": (
                f"{SOURCE_LABEL}:{quote(session_id, safe='')}:{record.primary_row_id}"
            ),
            "source": SOURCE_LABEL,
            "confidence": _CONFIDENCE.get(record.kind, 0.8),
            "provenance": _PROVENANCE.get(record.kind, "imported"),
            "status": "active",
            **({"type": record.memanto_type} if record.memanto_type else {}),
        },
    }
    front = "\n".join(_yaml_block(frontmatter))
    return f"---\n{front}\n---\n\n{body}\n"


def source_uri(session_id: str, messages_table: str, row_id: int) -> str:
    """Stable identifier for one source item.

    Deliberately path-free: the local database filename is environment-specific
    (and not something to publish into a memory), so identity is
    session + table + rowid. The file path and its hash live in the report.

    A session id is arbitrary user data — it may hold spaces, ``/``, ``?``, ``#``
    or non-ASCII — so it is percent-encoded as one component. ``messages_table``
    is already restricted to a plain SQL identifier and ``row_id`` is an int, so
    neither needs encoding. Ids made only of unreserved characters (the common
    case) come out byte-identical.
    """
    return (
        f"openai-agents-sqlite://{quote(session_id, safe='')}/{messages_table}/{row_id}"
    )


def _provenance_block(record: Record, session_id: str, messages_table: str) -> str:
    ids = ", ".join(f"`{messages_table}:{row_id}`" for row_id in record.row_ids)
    parts = [
        "**Provenance** — OpenAI Agents SDK `SQLiteSession`",
        f"session `{session_id}`",
        f"item {ids}",
    ]
    if record.role:
        parts.append(f"role `{record.role}`")
    if record.timestamp:
        parts.append(f"recorded `{record.timestamp}`")
    return " · ".join(parts) + "."


def document_path(record: Record) -> str:
    """Bundle-relative path for a record — ordered by source row id, so the
    directory listing reads in conversation order."""
    slug = _slugify(record.title.split("·")[-1], fallback=record.kind)
    return f"memories/{record.kind}/{record.primary_row_id:04d}-{slug}.md"


# ---------------------------------------------------------------------------
# Bundle writing
# ---------------------------------------------------------------------------


def _render_index(
    heading: str,
    lines: list[str],
    links: list[tuple[str, str]],
    *,
    root: bool = False,
) -> str:
    """Render a reserved ``index.md`` (OKF 0.2 §8).

    Index files carry no frontmatter; the one exception the spec allows is an
    ``okf_version`` key on the bundle-root index, which is where the bundle
    declares the format version.
    """
    out: list[str] = []
    if root:
        front = "\n".join(_yaml_block({"okf_version": OKF_VERSION}))
        out.append(f"---\n{front}\n---")
        out.append("")
    out.extend([GENERATOR_MARKER, "", f"# {heading}", ""])
    out.extend(lines)
    if lines:
        out.append("")
    out.extend(f"- [{text}]({href})" for text, href in links)
    out.append("")
    return "\n".join(out)


def write_bundle(
    result: Transformed,
    out_dir: Path,
    *,
    messages_table: str,
    session_meta: dict[str, str | None],
    force: bool = False,
) -> list[Path]:
    """Write the OKF bundle. Returns the written paths, sorted."""
    out_dir = Path(out_dir)
    _prepare_output_dir(out_dir, force=force)

    written: list[Path] = []
    by_kind: dict[str, list[Record]] = {}
    for record in result.records:
        by_kind.setdefault(record.kind, []).append(record)

    for kind in sorted(by_kind):
        records = sorted(by_kind[kind], key=lambda r: r.primary_row_id)
        kind_dir = out_dir / "memories" / kind
        kind_dir.mkdir(parents=True, exist_ok=True)
        links: list[tuple[str, str]] = []
        for record in records:
            rel = document_path(record)
            path = out_dir / rel
            path.write_text(
                render_document(record, result.session_id, messages_table),
                encoding="utf-8",
            )
            written.append(path)
            links.append((record.title, Path(rel).name))
        index = kind_dir / "index.md"
        index.write_text(
            _render_index(
                f"{kind} ({len(records)})",
                [f"OKF type `openai-agents.{kind}` — {len(records)} document(s)."],
                links,
            ),
            encoding="utf-8",
        )
        written.append(index)

    memories_index = out_dir / "memories" / "index.md"
    memories_index.parent.mkdir(parents=True, exist_ok=True)
    memories_index.write_text(
        _render_index(
            f"Memories ({len(result.records)})",
            [],
            [(kind, f"{kind}/index.md") for kind in sorted(by_kind)],
        ),
        encoding="utf-8",
    )
    written.append(memories_index)

    root_index = out_dir / "index.md"
    root_index.write_text(
        _render_index(
            f"{result.session_id} — OKF {OKF_VERSION} bundle",
            _root_index_lines(result, by_kind, session_meta),
            [("memories", "memories/index.md")],
            root=True,
        ),
        encoding="utf-8",
    )
    written.append(root_index)

    return sorted(written)


def _root_index_lines(
    result: Transformed,
    by_kind: dict[str, list[Record]],
    session_meta: dict[str, str | None],
) -> list[str]:
    counts = ", ".join(f"{kind}: {len(recs)}" for kind, recs in sorted(by_kind.items()))
    lines = [
        f"> Source: OpenAI Agents SDK `SQLiteSession` · session `{result.session_id}`",
        "",
        f"- OKF version: {OKF_VERSION}",
        f"- Generated by: `{ADAPTER_NAME}` {ADAPTER_VERSION}",
        f"- Documents: {len(result.records)} ({counts or 'none'})",
        f"- Source items skipped: {len(result.skipped)}",
    ]
    created = _iso(session_meta.get("created_at"))
    if created:
        lines.append(f"- Session created: {created}")
    updated = _iso(session_meta.get("updated_at"))
    if updated:
        lines.append(f"- Session last updated: {updated}")
    stamps = sorted(r.timestamp for r in result.records if r.timestamp)
    if stamps:
        lines.append(f"- Item timestamps: {stamps[0]} .. {stamps[-1]}")
    undated = sum(1 for r in result.records if not r.timestamp)
    if undated:
        lines.append(f"- Documents without a usable source timestamp: {undated}")
    return lines


def _prepare_output_dir(out_dir: Path, *, force: bool) -> None:
    """Create (or safely reset) the bundle directory.

    Refuses to touch a non-empty directory that the adapter did not write, even
    with ``--force``: the marker in ``index.md`` is the proof of ownership.
    """
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
        return
    if not out_dir.is_dir():
        raise AdapterError(f"Output path is not a directory: {out_dir}")
    if not any(out_dir.iterdir()):
        return

    index = out_dir / "index.md"
    owned = index.is_file() and GENERATOR_MARKER in index.read_text(encoding="utf-8")
    if not owned:
        raise AdapterError(
            f"Refusing to write into non-empty directory {out_dir}: it was not "
            f"produced by {ADAPTER_NAME}."
        )
    if not force:
        raise AdapterError(
            f"{out_dir} already holds a bundle. Re-run with --force to replace it."
        )
    shutil.rmtree(out_dir / "memories", ignore_errors=True)
    index.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _tally(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_report(
    *,
    result: Transformed,
    rows: list[SourceRow],
    db_path: Path,
    read_snapshot_sha256: str,
    out_dir: Path,
    written: list[Path],
    messages_table: str,
    sessions_table: str,
    session_meta: dict[str, str | None],
    source_package_version: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the migration evidence report (source / mapped / skipped)."""
    documents = [p for p in written if p.name != "index.md"]
    stamps = sorted(r.timestamp for r in result.records if r.timestamp)
    return {
        "adapter": {
            "name": ADAPTER_NAME,
            "version": ADAPTER_VERSION,
            "okf_version": OKF_VERSION,
        },
        "source": {
            "tool": "openai-agents (OpenAI Agents SDK) SQLiteSession",
            "package_version": source_package_version,
            "db_file": db_path.name,
            # sha256 of the consistent read snapshot (see consistent_snapshot),
            # NOT of the raw .db: under WAL the main file is byte-identical for
            # two different logical states, so hashing it proves nothing.
            "read_snapshot_sha256": read_snapshot_sha256,
            "sessions_table": sessions_table,
            "messages_table": messages_table,
            "session_id": result.session_id,
            "session_created_at": _iso(session_meta.get("created_at")),
            "session_updated_at": _iso(session_meta.get("updated_at")),
        },
        "counts": {
            "source_items": len(rows),
            "mapped_documents": len(result.records),
            "skipped_items": len(result.skipped),
            "source_items_consumed": sum(len(r.row_ids) for r in result.records)
            + len(result.skipped),
            # Documents whose source timestamp was absent or not ISO 8601: they
            # carry no `timestamp` / `generated` block (see _iso).
            "mapped_without_timestamp": sum(
                1 for r in result.records if not r.timestamp
            ),
            "mapped_by_kind": _tally([r.kind for r in result.records]),
            "skipped_by_reason": _tally([s.reason for s in result.skipped]),
            "memanto_type_hints": _tally(
                [r.memanto_type or "auto (Memanto classifies)" for r in result.records]
            ),
        },
        "skipped": [
            {
                "source_item": f"{messages_table}:{s.row_id}",
                "reason": s.reason,
                "detail": s.detail,
            }
            for s in result.skipped
        ],
        "mapped": [
            {
                "source_items": [f"{messages_table}:{i}" for i in r.row_ids],
                "resource": source_uri(
                    result.session_id, messages_table, r.primary_row_id
                ),
                "kind": r.kind,
                "role": r.role,
                "turn": r.turn,
                "timestamp": r.timestamp,
                "memanto_type": r.memanto_type or "auto",
                "okf_document": document_path(r),
            }
            for r in sorted(result.records, key=lambda r: r.primary_row_id)
        ],
        "output": {
            "bundle_dir": out_dir.name,
            "files": sorted(str(p.relative_to(out_dir).as_posix()) for p in written),
            "documents": len(documents),
            "item_timestamp_range": [stamps[0], stamps[-1]] if stamps else [],
        },
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def migrate(
    *,
    db_path: Path,
    session_id: str,
    out_dir: Path,
    messages_table: str = "agent_messages",
    sessions_table: str = "agent_sessions",
    force: bool = False,
    source_package_version: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Read -> transform -> write -> report. The whole adapter in one call.

    Every read — rows, metadata and the evidence hash — comes from one
    transactionally consistent snapshot, so the report can never describe a mix
    of two states (see ``consistent_snapshot``).
    """
    with consistent_snapshot(db_path) as snapshot:
        rows = read_rows(
            snapshot,
            session_id,
            messages_table=messages_table,
            source_label=str(db_path),
        )
        session_meta = read_session_meta(
            snapshot, session_id, sessions_table=sessions_table
        )
        read_snapshot_sha256 = _sha256(snapshot)

    result = transform(rows, session_id)
    written = write_bundle(
        result,
        out_dir,
        messages_table=messages_table,
        session_meta=session_meta,
        force=force,
    )
    return build_report(
        result=result,
        rows=rows,
        db_path=db_path,
        read_snapshot_sha256=read_snapshot_sha256,
        out_dir=out_dir,
        written=written,
        messages_table=messages_table,
        sessions_table=sessions_table,
        session_meta=session_meta,
        source_package_version=source_package_version,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="okf_adapter.py",
        description=(
            "Convert an OpenAI Agents SDK SQLiteSession into an OKF "
            f"{OKF_VERSION} bundle that 'memanto migrate okf' can import."
        ),
    )
    parser.add_argument(
        "--db", required=True, type=Path, help="Path to the SDK's SQLite database."
    )
    parser.add_argument("--session", help="Session id to migrate.")
    parser.add_argument("--out", type=Path, help="Output OKF bundle directory.")
    parser.add_argument(
        "--messages-table",
        default="agent_messages",
        help="Messages table name (SDK default: agent_messages).",
    )
    parser.add_argument(
        "--sessions-table",
        default="agent_sessions",
        help="Sessions table name (SDK default: agent_sessions).",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List the sessions in the database and exit.",
    )
    parser.add_argument(
        "--report", type=Path, help="Write the migration report JSON here."
    )
    parser.add_argument(
        "--source-package-version",
        help="openai-agents version that produced the database (recorded in the report).",
    )
    parser.add_argument(
        "--generated-at",
        help="Override the report's generated_at stamp (for reproducible evidence).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing bundle in --out."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.list_sessions:
            sessions = list_sessions(
                args.db,
                sessions_table=args.sessions_table,
                messages_table=args.messages_table,
            )
            if not sessions:
                print("No sessions found.")
                return 0
            print(f"{'session_id':<32} {'items':>6}  updated_at")
            for info in sessions:
                print(
                    f"{info.session_id:<32} {info.item_count:>6}  "
                    f"{info.updated_at or '-'}"
                )
            return 0

        if not args.session or not args.out:
            print(
                "error: --session and --out are required (or use --list-sessions)",
                file=sys.stderr,
            )
            return 2

        report = migrate(
            db_path=args.db,
            session_id=args.session,
            out_dir=args.out,
            messages_table=args.messages_table,
            sessions_table=args.sessions_table,
            force=args.force,
            source_package_version=args.source_package_version,
            generated_at=args.generated_at,
        )
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    counts = report["counts"]
    print(f"Session      : {report['source']['session_id']}")
    print(f"Source items : {counts['source_items']}")
    print(
        f"Mapped docs  : {counts['mapped_documents']} "
        f"({', '.join(f'{k}={v}' for k, v in counts['mapped_by_kind'].items()) or '—'})"
    )
    print(
        f"Skipped items: {counts['skipped_items']} "
        f"({', '.join(f'{k}={v}' for k, v in counts['skipped_by_reason'].items()) or '—'})"
    )
    print(f"OKF bundle   : {args.out}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Report       : {args.report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

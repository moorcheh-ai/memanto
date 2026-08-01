#!/usr/bin/env python3
"""Export durable Google ADK SQLite session state as an OKF bundle.

The adapter is deliberately dependency-free. It reads the current JSON-backed
``SqliteSessionService`` schema in read-only mode, preserves a replayable source
snapshot, converts current durable state into importable OKF concepts, and
keeps session transcripts and superseded values outside ``memories/`` so an
OKF import cannot accidentally reactivate stale facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ADAPTER_VERSION = "1.0.0"
SNAPSHOT_SCHEMA = "google-adk-sqlite-snapshot/v1"
MANIFEST_SCHEMA = "google-adk-okf-manifest/v1"
SOURCE_SCHEMA = "google-adk-sqlite-json/v1"
MEMANTO_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}
REQUIRED_COLUMNS = {
    "app_states": {"app_name", "state", "update_time"},
    "user_states": {"app_name", "user_id", "state", "update_time"},
    "sessions": {
        "app_name",
        "user_id",
        "id",
        "state",
        "create_time",
        "update_time",
    },
    "events": {
        "id",
        "app_name",
        "user_id",
        "session_id",
        "invocation_id",
        "timestamp",
        "event_data",
    },
}
SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_.:-])(api[_-]?key|authorization|cookie|credential|password|"
    r"private[_-]?key|secret|session[_-]?token|token)(?:$|[_.:-])",
    re.IGNORECASE,
)
TYPE_ALIASES = {
    "facts": "fact",
    "preferences": "preference",
    "goals": "goal",
    "decisions": "decision",
    "artifacts": "artifact",
    "learnings": "learning",
    "events": "event",
    "instructions": "instruction",
    "relationships": "relationship",
    "contexts": "context",
    "observations": "observation",
    "commitments": "commitment",
    "errors": "error",
    "policy": "instruction",
    "policies": "instruction",
    "profile": "fact",
}
SCOPE_CONFIDENCE = {"app": 0.90, "user": 0.95, "session": 0.85}


class AdapterError(RuntimeError):
    """A migration error with an actionable message for the user."""


def canonical_json(value: Any, *, pretty: bool = False) -> str:
    """Serialize JSON deterministically while retaining Unicode."""
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return (
            datetime.fromtimestamp(number, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def slugify(value: str, *, limit: int = 64) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:limit].rstrip("-") or "item"


def _json_object(value: Any, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"Invalid JSON in {label}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise AdapterError(f"Expected a JSON object in {label}")
    return decoded


def _is_sensitive_key(key: str) -> bool:
    """Recognize delimited and camelCase credential field names."""
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", normalized)
    return bool(SENSITIVE_KEY_RE.search(normalized))


def _redacted_marker() -> str:
    # Do not publish a digest of the raw value: low-entropy passwords and PINs
    # are recoverable from an unsalted hash even when the digest is truncated.
    return "<redacted>"


def redact_value(value: Any, *, key: str = "") -> tuple[Any, int]:
    """Redact values whose field name clearly denotes a credential."""
    if key and _is_sensitive_key(key):
        return _redacted_marker(), 1
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        total = 0
        for child_key, child_value in value.items():
            clean, count = redact_value(child_value, key=str(child_key))
            result[str(child_key)] = clean
            total += count
        return result, total
    if isinstance(value, list):
        result_list = []
        total = 0
        for child in value:
            clean, count = redact_value(child)
            result_list.append(clean)
            total += count
        return result_list, total
    return value, 0


def _readonly_uri(path: Path) -> str:
    # pathlib's file URI is correctly escaped on POSIX and Windows. SQLite
    # accepts the standard file:///C:/... form when ``uri=True``.
    return f"{path.resolve().as_uri()}?mode=ro"


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    quoted = table.replace('"', '""')
    return {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
    }


def validate_source_schema(connection: sqlite3.Connection) -> dict[str, list[str]]:
    """Fail closed when the database is not the expected ADK JSON schema."""
    found_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing_tables = sorted(set(REQUIRED_COLUMNS) - found_tables)
    if missing_tables:
        raise AdapterError(
            "Not a current Google ADK SqliteSessionService database; missing "
            f"table(s): {', '.join(missing_tables)}"
        )

    schema: dict[str, list[str]] = {}
    mismatches = []
    for table, required in REQUIRED_COLUMNS.items():
        columns = _table_columns(connection, table)
        schema[table] = sorted(columns)
        missing = sorted(required - columns)
        if missing:
            mismatches.append(f"{table}: {', '.join(missing)}")
    if mismatches:
        raise AdapterError(
            "The database uses an unsupported or legacy ADK schema (missing "
            + "; ".join(mismatches)
            + "). Migrate it with Google ADK's "
            "google.adk.sessions.migration tooling, then retry."
        )
    return schema


def _matches_scope(
    app_name: str,
    user_id: str | None,
    *,
    app_filter: str | None,
    user_filter: str | None,
) -> bool:
    if app_filter is not None and app_name != app_filter:
        return False
    return user_filter is None or user_id == user_filter


def snapshot_database(
    database: str | Path,
    *,
    app_filter: str | None = None,
    user_filter: str | None = None,
    redact: bool = True,
    captured_at: str | None = None,
    source_version: str | None = None,
) -> dict[str, Any]:
    """Capture a normalized, replayable snapshot from an ADK SQLite DB."""
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise AdapterError(f"Google ADK SQLite database not found: {path}")

    database_sha256 = sha256_file(path)
    redactions = 0
    with closing(sqlite3.connect(_readonly_uri(path), uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        schema = validate_source_schema(connection)

        eligible_user_apps: set[str] | None = None
        if user_filter is not None:
            eligible_user_apps = {
                str(row[0])
                for row in connection.execute(
                    "SELECT app_name FROM user_states WHERE user_id=? "
                    "UNION SELECT app_name FROM sessions WHERE user_id=?",
                    (user_filter, user_filter),
                ).fetchall()
            }
            if app_filter is not None:
                eligible_user_apps &= {app_filter}

        app_rows = []
        for row in connection.execute(
            "SELECT app_name, state, update_time FROM app_states ORDER BY app_name"
        ):
            if not _matches_scope(
                row["app_name"],
                None,
                app_filter=app_filter,
                user_filter=None,
            ):
                continue
            if (
                eligible_user_apps is not None
                and row["app_name"] not in eligible_user_apps
            ):
                continue
            state = _json_object(row["state"], label=f"app_states/{row['app_name']}")
            if redact:
                state, count = redact_value(state)
                redactions += count
            app_rows.append(
                {
                    "app_name": row["app_name"],
                    "state": state,
                    "update_time": iso_timestamp(row["update_time"]),
                }
            )

        user_rows = []
        for row in connection.execute(
            "SELECT app_name, user_id, state, update_time "
            "FROM user_states ORDER BY app_name, user_id"
        ):
            if not _matches_scope(
                row["app_name"],
                row["user_id"],
                app_filter=app_filter,
                user_filter=user_filter,
            ):
                continue
            state = _json_object(
                row["state"],
                label=f"user_states/{row['app_name']}/{row['user_id']}",
            )
            if redact:
                state, count = redact_value(state)
                redactions += count
            user_rows.append(
                {
                    "app_name": row["app_name"],
                    "user_id": row["user_id"],
                    "state": state,
                    "update_time": iso_timestamp(row["update_time"]),
                }
            )

        sessions = []
        session_rows = connection.execute(
            "SELECT app_name, user_id, id, state, create_time, update_time "
            "FROM sessions ORDER BY app_name, user_id, create_time, id"
        ).fetchall()
        for row in session_rows:
            if not _matches_scope(
                row["app_name"],
                row["user_id"],
                app_filter=app_filter,
                user_filter=user_filter,
            ):
                continue
            state = _json_object(
                row["state"],
                label=f"sessions/{row['app_name']}/{row['user_id']}/{row['id']}",
            )
            if redact:
                state, count = redact_value(state)
                redactions += count

            events = []
            event_rows = connection.execute(
                "SELECT id, invocation_id, timestamp, event_data FROM events "
                "WHERE app_name=? AND user_id=? AND session_id=? "
                "ORDER BY timestamp, id",
                (row["app_name"], row["user_id"], row["id"]),
            ).fetchall()
            for event_row in event_rows:
                event_data = _json_object(
                    event_row["event_data"],
                    label=f"events/{row['id']}/{event_row['id']}",
                )
                if redact:
                    event_data, count = redact_value(event_data)
                    redactions += count
                events.append(
                    {
                        "id": event_row["id"],
                        "invocation_id": event_row["invocation_id"],
                        "timestamp": iso_timestamp(event_row["timestamp"]),
                        "event_data": event_data,
                    }
                )
            sessions.append(
                {
                    "app_name": row["app_name"],
                    "user_id": row["user_id"],
                    "session_id": row["id"],
                    "state": state,
                    "create_time": iso_timestamp(row["create_time"]),
                    "update_time": iso_timestamp(row["update_time"]),
                    "events": events,
                }
            )

    if not app_rows and not user_rows and not sessions:
        scope = ", ".join(
            value
            for value in (
                f"app={app_filter!r}" if app_filter else "",
                f"user={user_filter!r}" if user_filter else "",
            )
            if value
        )
        raise AdapterError(f"No Google ADK data matched the requested scope ({scope})")

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "source": {
            "provider": "google-adk",
            "service": "SqliteSessionService",
            "schema": SOURCE_SCHEMA,
            "database_name": path.name,
            "database_sha256": database_sha256,
            "google_adk_version": source_version,
            "captured_at": captured_at or utc_now(),
            "redaction_enabled": redact,
            "redacted_values": redactions,
            "table_columns": schema,
        },
        "filters": {"app_name": app_filter, "user_id": user_filter},
        "app_states": app_rows,
        "user_states": user_rows,
        "sessions": sessions,
    }
    return snapshot


def load_snapshot(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    try:
        snapshot = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"Could not read snapshot {source_path}: {exc}") from exc
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise AdapterError(
            f"Unsupported snapshot schema in {source_path}; expected {SNAPSHOT_SCHEMA}"
        )
    for field in ("source", "app_states", "user_states", "sessions"):
        if field not in snapshot:
            raise AdapterError(f"Snapshot is missing required field: {field}")
    return snapshot


def _state_target(
    session: dict[str, Any], raw_key: str
) -> tuple[str, str, str | None, str | None, str]:
    if raw_key.startswith("app:"):
        return ("app", session["app_name"], None, None, raw_key[4:])
    if raw_key.startswith("user:"):
        return (
            "user",
            session["app_name"],
            session["user_id"],
            None,
            raw_key[5:],
        )
    if raw_key.startswith("temp:"):
        return ("temp", session["app_name"], session["user_id"], None, raw_key)
    return (
        "session",
        session["app_name"],
        session["user_id"],
        session["session_id"],
        raw_key,
    )


def _event_state_delta(event_data: dict[str, Any]) -> dict[str, Any]:
    actions = event_data.get("actions") or {}
    if not isinstance(actions, dict):
        return {}
    delta = actions.get("stateDelta", actions.get("state_delta", {}))
    return delta if isinstance(delta, dict) else {}


def state_histories(
    snapshot: dict[str, Any],
) -> dict[tuple[str, str, str | None, str | None, str], list[dict[str, Any]]]:
    """Recover durable state updates from the persisted ADK event log."""
    result: dict[tuple[str, str, str | None, str | None, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for session in snapshot.get("sessions", []):
        for event in session.get("events", []):
            event_data = event.get("event_data") or {}
            for raw_key, value in _event_state_delta(event_data).items():
                target = _state_target(session, str(raw_key))
                if target[0] == "temp":
                    continue
                result[target].append(
                    {
                        "timestamp": event.get("timestamp"),
                        "event_id": event.get("id"),
                        "invocation_id": event.get("invocation_id"),
                        "author": event_data.get("author"),
                        "value": value,
                    }
                )
    for updates in result.values():
        # App- and user-scoped deltas can arrive from overlapping sessions, so
        # session iteration order is not necessarily chronological.
        updates.sort(
            key=lambda item: (
                item.get("timestamp") or "",
                str(item.get("event_id") or ""),
            )
        )
    return result


def infer_memory_type(key: str) -> str:
    tokens = [token for token in re.split(r"[.:/_-]+", key.lower()) if token]
    for token in tokens:
        mapped = TYPE_ALIASES.get(token, token)
        if mapped in MEMANTO_TYPES:
            return mapped
    joined = " ".join(tokens)
    heuristics = (
        ("prefer", "preference"),
        ("owner", "relationship"),
        ("dri", "relationship"),
        ("deadline", "commitment"),
        ("plan", "goal"),
        ("rule", "instruction"),
        ("format", "preference"),
        ("failure", "error"),
        ("lesson", "learning"),
    )
    for needle, memory_type in heuristics:
        if needle in joined:
            return memory_type
    return "context"


def _title_from_key(key: str) -> str:
    tokens = [token for token in re.split(r"[.:/_-]+", key) if token]
    if tokens and (
        tokens[0].lower() in MEMANTO_TYPES or tokens[0].lower() in TYPE_ALIASES
    ):
        tokens = tokens[1:]
    title = " ".join(tokens or [key]).strip()
    return title[:1].upper() + title[1:]


def _content_from_value(
    title: str, value: Any
) -> tuple[str, str, list[str], float | None]:
    if isinstance(value, dict):
        override_title = str(value.get("title") or title).strip()
        raw_content = value.get("content", value.get("text", value.get("value")))
        tags = (
            [str(tag) for tag in value.get("tags", []) if tag]
            if isinstance(value.get("tags"), list)
            else []
        )
        confidence = value.get("confidence")
        try:
            parsed_confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            parsed_confidence = None
        if raw_content not in (None, ""):
            return override_title, str(raw_content).strip(), tags, parsed_confidence
        return (
            override_title,
            canonical_json(value, pretty=True),
            tags,
            parsed_confidence,
        )
    if isinstance(value, str):
        return title, value.strip(), [], None
    return title, canonical_json(value, pretty=True), [], None


def _concept_id(target: tuple[str, str, str | None, str | None, str]) -> str:
    digest = sha256_bytes(canonical_json(target).encode("utf-8"))[:12]
    return f"adk-{target[0]}-{slugify(target[-1], limit=38)}-{digest}"


def _target_resource(
    snapshot: dict[str, Any],
    target: tuple[str, str, str | None, str | None, str],
) -> str:
    scope, app_name, user_id, session_id, key = target
    database_id = snapshot["source"]["database_sha256"][:16]
    pieces = [database_id, app_name, scope]
    if user_id is not None:
        pieces.append(user_id)
    if session_id is not None:
        pieces.append(session_id)
    pieces.append(key)
    return "google-adk://sqlite/" + "/".join(
        quote(str(piece), safe="") for piece in pieces
    )


def build_concepts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Map current durable state entries to typed OKF concepts."""
    histories = state_histories(snapshot)
    concepts = []

    def add_state(
        *,
        scope: str,
        app_name: str,
        user_id: str | None,
        session_id: str | None,
        state: dict[str, Any],
        update_time: str | None,
    ) -> None:
        for key in sorted(state):
            value = state[key]
            target = (scope, app_name, user_id, session_id, str(key))
            history = list(histories.get(target, []))
            if history and canonical_json(history[-1].get("value")) != canonical_json(
                value
            ):
                # A database can be updated outside the retained event window.
                # The current state table remains authoritative, so make that
                # final transition explicit rather than mislabeling an older
                # event value as current.
                history.append(
                    {
                        "timestamp": update_time,
                        "event_id": None,
                        "invocation_id": None,
                        "author": "state-table",
                        "value": value,
                    }
                )
            title, content, extra_tags, explicit_confidence = _content_from_value(
                _title_from_key(str(key)), value
            )
            if not content:
                continue
            memory_type = infer_memory_type(str(key))
            first_time = next(
                (item.get("timestamp") for item in history if item.get("timestamp")),
                update_time,
            )
            last_time = next(
                (
                    item.get("timestamp")
                    for item in reversed(history)
                    if item.get("timestamp")
                ),
                update_time,
            )
            confidence = (
                max(0.0, min(1.0, explicit_confidence))
                if explicit_confidence is not None
                else SCOPE_CONFIDENCE[scope]
            )
            tags = {
                "source:google-adk",
                f"scope:{scope}",
                f"app:{slugify(app_name)}",
                f"type:{memory_type}",
                *extra_tags,
            }
            if user_id:
                tags.add(f"user:{slugify(user_id)}")
            if session_id:
                tags.add(f"session:{slugify(session_id)}")
            distinct_values = {
                canonical_json(value),
                *(canonical_json(item.get("value")) for item in history),
            }
            concepts.append(
                {
                    "id": _concept_id(target),
                    "title": title,
                    "content": content,
                    "type": memory_type,
                    "tags": sorted(tags),
                    "confidence": confidence,
                    "created_at": first_time,
                    "updated_at": last_time,
                    "resource": _target_resource(snapshot, target),
                    "target": target,
                    "state_key": str(key),
                    "scope": scope,
                    "app_name": app_name,
                    "user_id": user_id,
                    "session_id": session_id,
                    "current_value": value,
                    "history": history,
                    "distinct_values": len(distinct_values),
                }
            )

    for row in snapshot.get("app_states", []):
        add_state(
            scope="app",
            app_name=row["app_name"],
            user_id=None,
            session_id=None,
            state=row.get("state") or {},
            update_time=row.get("update_time"),
        )
    for row in snapshot.get("user_states", []):
        add_state(
            scope="user",
            app_name=row["app_name"],
            user_id=row["user_id"],
            session_id=None,
            state=row.get("state") or {},
            update_time=row.get("update_time"),
        )
    for row in snapshot.get("sessions", []):
        add_state(
            scope="session",
            app_name=row["app_name"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            state=row.get("state") or {},
            update_time=row.get("update_time"),
        )
    return sorted(concepts, key=lambda item: (item["type"], item["id"]))


def _frontmatter(data: dict[str, Any]) -> str:
    # JSON is a strict subset of YAML, so this remains a valid OKF YAML
    # frontmatter block without adding a runtime dependency to the adapter.
    return f"---\n{canonical_json(data, pretty=True)}\n---"


def _relative_audit_path(concept: dict[str, Any]) -> str:
    return f"../../archive/state-history/{concept['id']}.md"


def render_concept(concept: dict[str, Any], captured_at: str) -> str:
    front = {
        "type": concept["type"],
        "title": concept["title"],
        # OKF loaders may prefer description to body. Preserve the complete
        # concept so the imported value cannot be silently truncated.
        "description": concept["content"],
        "resource": concept["resource"],
        "tags": concept["tags"],
        "timestamp": concept["updated_at"] or captured_at,
        "status": "stable",
        "generated": {
            "at": captured_at,
            "by": f"memanto-google-adk-okf/{ADAPTER_VERSION}",
        },
        "sources": [
            {
                "id": concept["id"],
                "type": "google-adk-sqlite-state",
                "resource": concept["resource"],
            }
        ],
        "x_memanto": {
            "id": concept["id"],
            "type": concept["type"],
            "confidence": concept["confidence"],
            "provenance": "imported",
            "source": "google-adk",
            "status": "active",
        },
        "x_google_adk": {
            "app_name": concept["app_name"],
            "user_id": concept["user_id"],
            "session_id": concept["session_id"],
            "scope": concept["scope"],
            "state_key": concept["state_key"],
            "state_updates": len(concept["history"]),
            "distinct_values": concept["distinct_values"],
        },
    }
    lines = [
        _frontmatter(front),
        "",
        f"# {concept['title']}",
        "",
        concept["content"],
        "",
        "## Provenance",
        "",
        f"- Google ADK scope: `{concept['scope']}`",
        f"- State key: `{concept['state_key']}`",
        f"- App: `{concept['app_name']}`",
    ]
    if concept["user_id"]:
        lines.append(f"- User: `{concept['user_id']}`")
    if concept["session_id"]:
        lines.append(f"- Session: `{concept['session_id']}`")
    if concept["distinct_values"] > 1:
        lines.extend(
            [
                "",
                f"[Audit trail ({len(concept['history'])} persisted updates)]"
                f"({_relative_audit_path(concept)})",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_history(concept: dict[str, Any], captured_at: str) -> str:
    front = {
        "type": "state-history",
        "title": f"History: {concept['title']}",
        "resource": concept["resource"],
        "status": "deprecated",
        "generated": {
            "at": captured_at,
            "by": f"memanto-google-adk-okf/{ADAPTER_VERSION}",
        },
        "x_google_adk": {
            "scope": concept["scope"],
            "state_key": concept["state_key"],
            "current_concept": concept["id"],
        },
    }
    lines = [
        _frontmatter(front),
        "",
        f"# History: {concept['title']}",
        "",
        "> Audit-only. This file is outside `memories/` and is not imported as current truth.",
        "",
    ]
    for index, item in enumerate(concept["history"], 1):
        status = "current" if index == len(concept["history"]) else "superseded"
        lines.extend(
            [
                f"## Update {index} — {status}",
                "",
                f"- Timestamp: `{item.get('timestamp') or 'unknown'}`",
                f"- Event: `{item.get('event_id') or 'unknown'}`",
                f"- Author: `{item.get('author') or 'unknown'}`",
                "",
                "```json",
                canonical_json(item.get("value"), pretty=True),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _event_text(event_data: dict[str, Any]) -> str:
    content = event_data.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    texts = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            texts.append(part["text"].strip())
    return "\n".join(text for text in texts if text)


def render_session(session: dict[str, Any], captured_at: str) -> str:
    title = f"Google ADK session {session['session_id']}"
    events = session.get("events", [])
    first_event = next(
        (event.get("timestamp") for event in events if event.get("timestamp")),
        None,
    )
    last_event = next(
        (
            event.get("timestamp")
            for event in reversed(events)
            if event.get("timestamp")
        ),
        None,
    )
    front = {
        "type": "session",
        "title": title,
        "timestamp": session.get("update_time") or captured_at,
        "status": "stable",
        "generated": {
            "at": captured_at,
            "by": f"memanto-google-adk-okf/{ADAPTER_VERSION}",
        },
        "x_google_adk": {
            "app_name": session["app_name"],
            "user_id": session["user_id"],
            "session_id": session["session_id"],
            "events": len(events),
        },
    }
    lines = [
        _frontmatter(front),
        "",
        f"# {title}",
        "",
        f"- App: `{session['app_name']}`",
        f"- User: `{session['user_id']}`",
        f"- First persisted event: `{first_event or 'unknown'}`",
        f"- Last persisted event: `{last_event or 'unknown'}`",
        f"- Captured: `{captured_at}`",
        "",
        "> Context-only transcript. Memanto's OKF importer scopes imports to `memories/`.",
        "",
    ]
    for event in events:
        event_data = event.get("event_data") or {}
        author = str(event_data.get("author") or "unknown")
        text = _event_text(event_data)
        delta = _event_state_delta(event_data)
        lines.extend(
            [
                f"## {event.get('timestamp') or 'unknown'} — {author}",
                "",
                text or "_(non-text event retained in the source snapshot)_",
                "",
            ]
        )
        if delta:
            lines.extend(
                [
                    f"State updates: {', '.join(f'`{key}`' for key in sorted(delta))}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _write_index(
    directory: Path,
    *,
    title: str,
    links: Iterable[tuple[str, str]],
    timestamp: str,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        _frontmatter({"type": "index", "title": title, "timestamp": timestamp}),
        "",
        f"# {title}",
        "",
    ]
    lines.extend(f"- [{label}]({target})" for label, target in links)
    (directory / "index.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )


def _replace_directory(staging: Path, destination: Path, *, force: bool) -> None:
    if destination.exists() and not force:
        raise AdapterError(
            f"Output already exists: {destination}. Pass --force to replace it."
        )
    backup = destination.with_name(f".{destination.name}.backup")
    if backup.exists():
        raise AdapterError(f"Refusing to overwrite stale backup directory: {backup}")
    try:
        if destination.exists():
            destination.rename(backup)
        staging.rename(destination)
    except Exception:
        if backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def _file_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "migration-manifest.json"
    ]


def write_bundle(
    snapshot: dict[str, Any], output: str | Path, *, force: bool = False
) -> dict[str, Any]:
    """Write a complete OKF bundle and return its migration manifest."""
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise AdapterError(f"Expected snapshot schema {SNAPSHOT_SCHEMA}")
    destination = Path(output).expanduser().resolve()
    if not destination.name or destination == destination.parent:
        raise AdapterError(f"Unsafe output directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    captured_at = str(snapshot["source"].get("captured_at") or utc_now())
    concepts = build_concepts(snapshot)
    type_counts = Counter(concept["type"] for concept in concepts)

    try:
        memory_links: list[tuple[str, str]] = []
        for memory_type in sorted(type_counts):
            type_dir = staging / "memories" / memory_type
            links = []
            for concept in (item for item in concepts if item["type"] == memory_type):
                filename = f"{concept['id']}.md"
                (type_dir / filename).parent.mkdir(parents=True, exist_ok=True)
                (type_dir / filename).write_text(
                    render_concept(concept, captured_at), encoding="utf-8"
                )
                links.append((concept["title"], filename))
            _write_index(
                type_dir,
                title=f"{memory_type.title()} memories ({len(links)})",
                links=links,
                timestamp=captured_at,
            )
            memory_links.append(
                (f"{memory_type} ({len(links)})", f"{memory_type}/index.md")
            )
        _write_index(
            staging / "memories",
            title=f"Current Google ADK memories ({len(concepts)})",
            links=memory_links,
            timestamp=captured_at,
        )

        histories = [item for item in concepts if item["distinct_values"] > 1]
        history_links = []
        for concept in histories:
            filename = f"{concept['id']}.md"
            path = staging / "archive" / "state-history" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_history(concept, captured_at), encoding="utf-8")
            history_links.append((concept["title"], filename))
        if history_links:
            _write_index(
                staging / "archive" / "state-history",
                title=f"Superseded state audit ({len(history_links)})",
                links=history_links,
                timestamp=captured_at,
            )

        session_links = []
        for session in snapshot.get("sessions", []):
            digest = sha256_bytes(
                canonical_json(
                    [session["app_name"], session["user_id"], session["session_id"]]
                ).encode("utf-8")
            )[:10]
            filename = f"{slugify(session['session_id'], limit=48)}-{digest}.md"
            path = staging / "sessions" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_session(session, captured_at), encoding="utf-8")
            session_links.append((session["session_id"], filename))
        if session_links:
            _write_index(
                staging / "sessions",
                title=f"Google ADK session transcripts ({len(session_links)})",
                links=session_links,
                timestamp=captured_at,
            )

        source_dir = staging / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = source_dir / "google-adk-sqlite-snapshot.json"
        snapshot_path.write_text(
            canonical_json(snapshot, pretty=True) + "\n", encoding="utf-8"
        )

        events_count = sum(
            len(session.get("events", [])) for session in snapshot.get("sessions", [])
        )
        state_records = sum(
            len(row.get("state") or {})
            for section in ("app_states", "user_states", "sessions")
            for row in snapshot.get(section, [])
        )
        state_updates = sum(len(item["history"]) for item in concepts)
        root_links = [("Current memories", "memories/index.md")]
        if session_links:
            root_links.append(("Source session transcripts", "sessions/index.md"))
        if history_links:
            root_links.append(
                ("Superseded-state audit", "archive/state-history/index.md")
            )
        root_links.append(
            ("Replayable source snapshot", "source/google-adk-sqlite-snapshot.json")
        )
        _write_index(
            staging,
            title="Google ADK → OKF portable memory bundle",
            links=root_links,
            timestamp=captured_at,
        )

        manifest = {
            "schema": MANIFEST_SCHEMA,
            "adapter": {
                "name": "memanto-google-adk-okf",
                "version": ADAPTER_VERSION,
            },
            "source": {
                **snapshot["source"],
                "snapshot_path": "source/google-adk-sqlite-snapshot.json",
                "snapshot_sha256": sha256_file(snapshot_path),
            },
            "filters": snapshot.get("filters", {}),
            "migration": {
                "source_state_records": state_records,
                "mapped_memories": len(concepts),
                "skipped": state_records - len(concepts),
                "type_counts": dict(sorted(type_counts.items())),
                "sessions_preserved": len(snapshot.get("sessions", [])),
                "events_preserved": events_count,
                "state_updates_preserved": state_updates,
                "superseded_timelines_archived": len(histories),
                "redacted_values": snapshot["source"].get("redacted_values", 0),
            },
            "import_scope": "memories/",
            "files": _file_inventory(staging),
        }
        (staging / "migration-manifest.json").write_text(
            canonical_json(manifest, pretty=True) + "\n", encoding="utf-8"
        )
        _replace_directory(staging, destination, force=force)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Google ADK SqliteSessionService data to OKF."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path, help="Path to the ADK SQLite database")
    source.add_argument("--snapshot", type=Path, help="Replay a captured snapshot JSON")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--app", dest="app_filter", help="Only this ADK app")
    parser.add_argument("--user", dest="user_filter", help="Only this ADK user")
    parser.add_argument("--source-version", help="ADK version recorded in provenance")
    parser.add_argument(
        "--include-sensitive",
        action="store_true",
        help="Do not redact credential-like state fields (unsafe for public bundles)",
    )
    parser.add_argument("--captured-at", help="Override capture timestamp (ISO 8601)")
    parser.add_argument("--force", action="store_true", help="Replace output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.db:
            snapshot = snapshot_database(
                args.db,
                app_filter=args.app_filter,
                user_filter=args.user_filter,
                redact=not args.include_sensitive,
                captured_at=args.captured_at,
                source_version=args.source_version,
            )
        else:
            if args.app_filter or args.user_filter or args.captured_at:
                raise AdapterError(
                    "--app, --user, and --captured-at apply only to --db captures"
                )
            snapshot = load_snapshot(args.snapshot)
        manifest = write_bundle(snapshot, args.output, force=args.force)
    except (AdapterError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}")
        return 2
    migration = manifest["migration"]
    print(
        f"OK: {migration['source_state_records']} durable state records -> "
        f"{migration['mapped_memories']} OKF memories at {Path(args.output).resolve()}"
    )
    print("Next: memanto migrate okf <bundle> --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Convert Codex memories or session rollouts into an importable OKF bundle.

The preferred source is Codex's local ``memories_1.sqlite`` database.  It
contains the high-signal, secret-redacted memory records produced by Codex's
own memory pipeline.  A rollout JSONL file (or a directory of rollouts) is
also accepted as a bootstrap path when that database has not been populated.

Only user messages and final assistant answers are used from rollouts.
Developer messages, reasoning, commentary, tool calls, and tool outputs are
never copied into the bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ENTRY_DELIMITER = "<!-- okf-entry -->"
EXPORT_SCHEMA = "codex-stage1-memory-export/v1"
DEFAULT_SPLIT_THRESHOLD = 50
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 240
MAX_TAGS = 12

_TASK_RE = re.compile(r"(?m)^### Task\s+(\d+)(?::\s*|\s+)(.+?)\s*$")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_FIELD_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*?)\s*$")
_SECTION_RE = re.compile(
    r"(?m)^(Preference signals|Reusable knowledge|"
    r"Failures and how to do differently|References):\s*$"
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]{12,}"),
    ),
    (
        "openai_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    ),
    (
        "github_token",
        re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    (
        "aws_key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
            r"\.[A-Za-z0-9_-]{8,}\b"
        ),
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b((?:[A-Z][A-Z0-9_]*_)?"
            r"(?:TOKEN|SECRET|PASSWORD|API_KEY)(?:_[A-Z0-9]+)*)"
            r"\s*=\s*(?!\[REDACTED_SECRET\])"
            r"([^\s'\"`]{8,}|['\"][^'\"\n]{8,}['\"])"
        ),
    ),
)

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![\w.-])"
)
_HOME_PATH_PATTERNS = (
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"(?i)C:\\Users\\[^\\\s]+"),
)
_TEMP_PATH_PATTERNS = (
    re.compile(r"/private/tmp/[^/\s]+"),
    re.compile(r"/tmp/[^/\s]+"),
    re.compile(r"/var/folders/[^/\s]+/[^/\s]+/T/[^/\s]+"),
)

_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "decision",
        (
            " decided ",
            " decision ",
            " chose ",
            " selected ",
            " adopted ",
            " switched to ",
        ),
    ),
    (
        "preference",
        (
            "preference signals:",
            "prefers ",
            "user wants ",
            "the user asked",
            "the user corrected",
        ),
    ),
    (
        "instruction",
        (
            "must ",
            "always ",
            "never ",
            "instruction",
            "required workflow",
        ),
    ),
    (
        "goal",
        ("goal", "plans to", "working toward", "wants to build"),
    ),
)


@dataclass(frozen=True)
class SourceMemory:
    """One Codex stage-one memory record plus optional thread metadata."""

    thread_id: str
    raw_memory: str
    rollout_summary: str
    turn_id: str | None = None
    rollout_slug: str | None = None
    source_updated_at: int | str | None = None
    generated_at: int | str | None = None
    usage_count: int | None = None
    last_usage: int | str | None = None
    selected_for_phase2: bool | None = None
    cwd: str | None = None
    rollout_path: str | None = None
    git_branch: str | None = None
    cli_version: str | None = None
    thread_title: str | None = None
    source_kind: str = "stage1_memory"


@dataclass(frozen=True)
class PortableMemory:
    """One source task mapped onto a single OKF document."""

    title: str
    description: str
    body: str
    memory_type: str
    tags: tuple[str, ...]
    timestamp: str | None
    resource: str
    metadata: dict[str, Any]


@dataclass
class MigrationStats:
    """Auditable counts emitted beside the OKF bundle."""

    source_format: str
    source_records: int = 0
    source_tasks: int = 0
    mapped_memories: int = 0
    skipped_empty: int = 0
    malformed_lines: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)
    redactions: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_format": self.source_format,
            "source_records": self.source_records,
            "source_tasks": self.source_tasks,
            "mapped_memories": self.mapped_memories,
            "skipped_empty": self.skipped_empty,
            "malformed_lines": self.malformed_lines,
            "memories_by_type": dict(sorted(self.type_counts.items())),
            "redactions": dict(sorted(self.redactions.items())),
        }


class Redactor:
    """Defense-in-depth redaction for already-sanitized Codex memories."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def redact(self, text: str | None) -> str:
        if not text:
            return ""
        result = str(text)
        for label, pattern in _SECRET_PATTERNS:
            if label == "secret_assignment":
                result, count = pattern.subn(
                    lambda match: f"{match.group(1)}=[REDACTED_SECRET]", result
                )
            else:
                result, count = pattern.subn(f"[REDACTED_{label.upper()}]", result)
            self.counts[label] += count

        result, count = _EMAIL_RE.subn("[REDACTED_EMAIL]", result)
        self.counts["email"] += count

        for pattern in _HOME_PATH_PATTERNS:
            result, count = pattern.subn("~", result)
            self.counts["home_path"] += count
        for pattern in _TEMP_PATH_PATTERNS:
            result, count = pattern.subn("$TMPDIR", result)
            self.counts["temporary_path"] += count
        return result


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    has_wal = Path(f"{resolved}-wal").exists()
    # A cleanly closed WAL-mode database can retain its WAL header while
    # having no sidecar files. Immutable mode opens that snapshot without
    # creating a new -wal file. An existing WAL must remain visible so SQLite
    # can include its uncheckpointed records.
    query = "mode=ro" if has_wal else "mode=ro&immutable=1"
    connection = sqlite3.connect(f"{resolved.as_uri()}?{query}", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _has_table(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def discover_memory_db(codex_home: Path) -> Path:
    """Find the current or legacy Codex memory database below a Codex home."""

    candidates = (
        codex_home / "memories_1.sqlite",
        codex_home / "sqlite" / "memories_1.sqlite",
        codex_home / "state_5.sqlite",
        codex_home / "sqlite" / "state_5.sqlite",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        with closing(_connect_read_only(candidate)) as connection:
            if _has_table(connection, "stage1_outputs"):
                return candidate
    raise FileNotFoundError(
        f"No Codex database containing stage1_outputs found under {codex_home}"
    )


def discover_state_db(memory_db: Path) -> Path | None:
    """Find the companion state DB used to enrich memory provenance."""

    roots = (memory_db.parent, memory_db.parent.parent)
    for root in roots:
        for name in ("state_5.sqlite", "codex-dev.db"):
            candidate = root / name
            if not candidate.is_file() or candidate == memory_db:
                continue
            with closing(_connect_read_only(candidate)) as connection:
                if _has_table(connection, "threads"):
                    return candidate
    return None


def load_memory_database(
    memory_db: Path, state_db: Path | None = None
) -> list[SourceMemory]:
    """Read Codex stage-one outputs without modifying or locking the database."""

    with closing(_connect_read_only(memory_db)) as connection:
        if not _has_table(connection, "stage1_outputs"):
            raise ValueError(f"{memory_db} has no stage1_outputs table")
        columns = _table_columns(connection, "stage1_outputs")
        required = {
            "thread_id",
            "source_updated_at",
            "raw_memory",
            "rollout_summary",
            "generated_at",
        }
        missing = required - columns
        if missing:
            raise ValueError(
                f"{memory_db} is missing required columns: {sorted(missing)}"
            )

        optional = (
            "rollout_slug",
            "usage_count",
            "last_usage",
            "selected_for_phase2",
        )
        selected = sorted(required)
        selected.extend(column for column in optional if column in columns)
        query = (
            f"SELECT {', '.join(selected)} FROM stage1_outputs "
            "ORDER BY source_updated_at ASC, thread_id ASC"
        )
        rows = [dict(row) for row in connection.execute(query).fetchall()]

    thread_metadata = _load_thread_metadata(state_db) if state_db else {}
    memories: list[SourceMemory] = []
    for row in rows:
        metadata = thread_metadata.get(str(row["thread_id"]), {})
        memories.append(
            SourceMemory(
                thread_id=str(row["thread_id"]),
                raw_memory=str(row.get("raw_memory") or ""),
                rollout_summary=str(row.get("rollout_summary") or ""),
                rollout_slug=_optional_string(row.get("rollout_slug")),
                source_updated_at=row.get("source_updated_at"),
                generated_at=row.get("generated_at"),
                usage_count=_optional_int(row.get("usage_count")),
                last_usage=row.get("last_usage"),
                selected_for_phase2=(
                    bool(row["selected_for_phase2"])
                    if row.get("selected_for_phase2") is not None
                    else None
                ),
                cwd=_optional_string(metadata.get("cwd")),
                rollout_path=_optional_string(metadata.get("rollout_path")),
                git_branch=_optional_string(metadata.get("git_branch")),
                cli_version=_optional_string(metadata.get("cli_version")),
                thread_title=_optional_string(metadata.get("title")),
            )
        )
    return memories


def _load_thread_metadata(state_db: Path) -> dict[str, dict[str, Any]]:
    with closing(_connect_read_only(state_db)) as connection:
        if not _has_table(connection, "threads"):
            return {}
        columns = _table_columns(connection, "threads")
        wanted = (
            "id",
            "cwd",
            "rollout_path",
            "git_branch",
            "cli_version",
            "title",
        )
        selected = [column for column in wanted if column in columns]
        if "id" not in selected:
            return {}
        query = f"SELECT {', '.join(selected)} FROM threads"
        return {
            str(row["id"]): dict(row) for row in connection.execute(query).fetchall()
        }


def load_source_export(path: Path) -> list[SourceMemory]:
    """Load a portable, JSON-serialized snapshot of stage-one rows."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != EXPORT_SCHEMA:
        raise ValueError(
            f"{path} is not a {EXPORT_SCHEMA} export (schema field is missing)"
        )
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{path} has no records array")
    allowed = set(SourceMemory.__dataclass_fields__)
    memories = []
    required = {"thread_id", "raw_memory", "rollout_summary"}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        clean = {key: value for key, value in record.items() if key in allowed}
        missing = required - clean.keys()
        if missing:
            raise ValueError(
                f"{path} record {index} is missing required fields: {sorted(missing)}"
            )
        try:
            memories.append(SourceMemory(**clean))
        except TypeError as exc:
            raise ValueError(f"{path} record {index} is invalid: {exc}") from exc
    return memories


def write_source_export(
    memories: Iterable[SourceMemory],
    destination: Path,
    *,
    source_fingerprint: str,
    codex_version: str | None = None,
) -> None:
    """Write a reviewable snapshot without copying the SQLite database."""

    payload = {
        "schema": EXPORT_SCHEMA,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": source_fingerprint,
        "codex_version": codex_version,
        "records": [asdict(memory) for memory in memories],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_session_rollouts(
    source: Path, *, strict: bool, stats: MigrationStats
) -> list[SourceMemory]:
    """Build conservative task memories from persisted Codex event records."""

    files = [source] if source.is_file() else sorted(source.rglob("rollout-*.jsonl"))
    memories: list[SourceMemory] = []
    for file_path in files:
        parsed = _parse_rollout(file_path, strict=strict, stats=stats)
        memories.extend(parsed)
    return memories


def _parse_rollout(
    path: Path, *, strict: bool, stats: MigrationStats
) -> list[SourceMemory]:
    session_id = path.stem
    session_timestamp: str | None = None
    cwd: str | None = None
    cli_version: str | None = None
    git_branch: str | None = None
    current_turn_id: str | None = None
    user_message = ""
    final_answer = ""
    turn_timestamp: str | None = None
    memories: list[SourceMemory] = []

    def flush() -> None:
        nonlocal current_turn_id, user_message, final_answer, turn_timestamp
        if not user_message.strip() or not final_answer.strip():
            current_turn_id = None
            user_message = ""
            final_answer = ""
            turn_timestamp = None
            return
        title = _first_meaningful_line(user_message, fallback="Codex task")
        raw_memory = _session_turn_memory(
            title=title,
            user_message=user_message,
            final_answer=final_answer,
            cwd=cwd,
        )
        memories.append(
            SourceMemory(
                thread_id=session_id,
                raw_memory=raw_memory,
                rollout_summary=final_answer,
                turn_id=current_turn_id or f"turn-{len(memories) + 1}",
                rollout_slug=_slugify(title),
                source_updated_at=turn_timestamp or session_timestamp,
                cwd=cwd,
                rollout_path=str(path),
                git_branch=git_branch,
                cli_version=cli_version,
                thread_title=title,
                source_kind="session_rollout",
            )
        )
        current_turn_id = None
        user_message = ""
        final_answer = ""
        turn_timestamp = None

    for record in _iter_jsonl_records(path, strict=strict, stats=stats):
        record_type = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue

        if record_type == "session_meta":
            session_id = str(
                payload.get("session_id") or payload.get("id") or session_id
            )
            session_timestamp = _optional_string(
                payload.get("timestamp") or record.get("timestamp")
            )
            cwd = _optional_string(payload.get("cwd"))
            cli_version = _optional_string(payload.get("cli_version"))
            git = payload.get("git")
            if isinstance(git, dict):
                git_branch = _optional_string(git.get("branch"))
            continue

        if record_type != "event_msg":
            continue
        event_type = payload.get("type")
        if event_type == "task_started":
            flush()
            current_turn_id = _optional_string(payload.get("turn_id"))
            turn_timestamp = _optional_string(record.get("timestamp"))
        elif event_type == "user_message":
            user_message = str(payload.get("message") or "")
        elif event_type == "agent_message" and payload.get("phase") == "final_answer":
            final_answer = str(payload.get("message") or "")
        elif event_type == "task_complete":
            if not final_answer:
                final_answer = str(payload.get("last_agent_message") or "")
            current_turn_id = (
                _optional_string(payload.get("turn_id")) or current_turn_id
            )
            flush()
    flush()
    return memories


def _iter_jsonl_records(
    path: Path, *, strict: bool, stats: MigrationStats
) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                stats.malformed_lines += 1
                if strict:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSON: {exc}"
                    ) from exc
                continue
            if isinstance(record, dict):
                yield record


def _session_turn_memory(
    *, title: str, user_message: str, final_answer: str, cwd: str | None
) -> str:
    task_group = cwd or "codex-session"
    return (
        "---\n"
        f"description: {json.dumps('Completed Codex task: ' + title)}\n"
        f"task: {json.dumps(title)}\n"
        f"task_group: {json.dumps(task_group)}\n"
        "task_outcome: uncertain\n"
        f"cwd: {json.dumps(cwd or 'unknown')}\n"
        "keywords: codex, session, task-context\n"
        "---\n\n"
        f"### Task 1: {title}\n\n"
        f"task: {title}\n"
        f"task_group: {task_group}\n"
        "task_outcome: uncertain\n\n"
        "Reusable knowledge:\n"
        "User goal:\n\n"
        f"{user_message.strip()}\n\n"
        "Codex final answer:\n\n"
        f"{final_answer.strip()}\n"
    )


def map_source_memories(
    source_memories: Iterable[SourceMemory],
    *,
    redactor: Redactor,
    stats: MigrationStats,
) -> list[PortableMemory]:
    """Split Codex memory records into task-sized, provenance-rich OKF nodes."""

    mapped: list[PortableMemory] = []
    for source in source_memories:
        stats.source_records += 1
        raw_memory = redactor.redact(source.raw_memory).strip()
        rollout_summary = redactor.redact(source.rollout_summary).strip()
        safe_cwd = redactor.redact(source.cwd)
        safe_rollout_path = redactor.redact(source.rollout_path)
        safe_title = redactor.redact(source.thread_title)

        frontmatter, body = _parse_frontmatter(raw_memory)
        tasks = _split_tasks(body) if body.strip() else []
        if not tasks and rollout_summary:
            tasks = [(1, safe_title or "Codex rollout summary", rollout_summary)]
        if not tasks:
            stats.skipped_empty += 1
            continue

        keywords = _parse_keywords(frontmatter.get("keywords"))
        timestamp = _iso_timestamp(source.source_updated_at)
        for task_number, task_title, task_body in tasks:
            task_body = task_body.strip()
            if not task_body:
                stats.skipped_empty += 1
                continue
            stats.source_tasks += 1
            fields = _task_fields(task_body)
            outcome = fields.get("task_outcome") or frontmatter.get("task_outcome")
            memory_type = infer_memory_type(
                title=task_title, body=task_body, outcome=outcome
            )
            description = _truncate(
                str(frontmatter.get("description") or rollout_summary or task_title),
                MAX_DESCRIPTION_CHARS,
            )
            title = _truncate(task_title, MAX_TITLE_CHARS)
            task_group = (
                fields.get("task_group") or frontmatter.get("task_group") or safe_cwd
            )
            tags = _tags(
                (
                    "codex",
                    "agent-memory",
                    memory_type,
                    *(keywords or ()),
                    *((str(task_group),) if task_group else ()),
                )
            )
            thread_ref = quote(source.thread_id, safe="")
            fragment = f"task-{task_number}"
            if source.turn_id:
                turn_ref = quote(source.turn_id, safe="")
                resource = f"codex://thread/{thread_ref}/turn/{turn_ref}#{fragment}"
            else:
                resource = f"codex://thread/{thread_ref}#{fragment}"
            metadata = {
                "codex_source_kind": source.source_kind,
                "codex_thread_id": source.thread_id,
                "codex_turn_id": source.turn_id,
                "codex_task_number": task_number,
                "codex_task_outcome": outcome,
                "codex_task_group": task_group,
                "codex_rollout_slug": source.rollout_slug,
                "codex_cwd": safe_cwd or frontmatter.get("cwd"),
                "codex_rollout_path": safe_rollout_path,
                "codex_git_branch": redactor.redact(source.git_branch),
                "codex_cli_version": source.cli_version,
                "codex_generated_at": _iso_timestamp(source.generated_at),
                "codex_usage_count": source.usage_count,
                "codex_last_usage": _iso_timestamp(source.last_usage),
                "codex_selected_for_phase2": source.selected_for_phase2,
            }
            mapped.append(
                PortableMemory(
                    title=title,
                    description=description,
                    body=f"### Task {task_number}: {task_title}\n\n{task_body}",
                    memory_type=memory_type,
                    tags=tags,
                    timestamp=timestamp,
                    resource=resource,
                    metadata={
                        key: value
                        for key, value in metadata.items()
                        if value not in (None, "")
                    },
                )
            )
            stats.type_counts[memory_type] += 1

    stats.mapped_memories = len(mapped)
    stats.redactions.update(redactor.counts)
    return mapped


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        field_match = _FIELD_RE.match(line)
        if not field_match:
            continue
        key, value = field_match.groups()
        fields[key] = _parse_scalar(value)
    return fields, match.group(2)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[:1] in {'"', "[", "{"} or value in {"true", "false", "null"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _split_tasks(body: str) -> list[tuple[int, str, str]]:
    matches = list(_TASK_RE.finditer(body))
    if not matches:
        return [(1, _first_meaningful_line(body, fallback="Codex memory"), body)]
    tasks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        tasks.append(
            (
                int(match.group(1)),
                match.group(2).strip(),
                body[match.end() : end].strip(),
            )
        )
    return tasks


def _task_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines()[:12]:
        match = _FIELD_RE.match(line)
        if match and match.group(1) in {"task", "task_group", "task_outcome"}:
            fields[match.group(1)] = str(_parse_scalar(match.group(2)))
    return fields


def _section_has_content(body: str, section_name: str) -> bool:
    matches = list(_SECTION_RE.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1) != section_name:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[match.end() : end].strip()
        bullets = [
            line.strip().lstrip("-").strip()
            for line in section.splitlines()
            if line.strip().startswith("-") and len(line.strip()) > 2
        ]
        if section_name == "Failures and how to do differently":
            no_failure_prefixes = ("no failure", "none", "n/a", "not applicable")
            return any(
                not bullet.lower().startswith(no_failure_prefixes) for bullet in bullets
            )
        return bool(bullets)
    return False


def infer_memory_type(*, title: str, body: str, outcome: str | None) -> str:
    """Map a task block to the closest Memanto memory type."""

    normalized = f" {title} {body} ".lower()
    if str(outcome).lower() == "fail":
        return "error"
    has_preferences = _section_has_content(body, "Preference signals")
    has_reusable = _section_has_content(body, "Reusable knowledge")
    has_failures = _section_has_content(body, "Failures and how to do differently")
    if has_preferences and not has_reusable and not has_failures:
        return "preference"
    if has_failures:
        return "learning"
    for memory_type, phrases in _TYPE_RULES:
        if any(phrase in normalized for phrase in phrases):
            return memory_type
    if "task-context" in normalized or str(outcome).lower() == "uncertain":
        return "context"
    return "learning"


def write_okf_bundle(
    memories: list[PortableMemory],
    output_dir: Path,
    *,
    split: str,
    overwrite: bool,
    summary: dict[str, Any],
) -> None:
    """Write a navigable OKF bundle using Memanto's supported field set."""

    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{output_dir} already exists; pass --overwrite to replace it"
            )
        if not _is_generated_bundle(output_dir):
            raise FileExistsError(
                f"refusing to overwrite {output_dir}: it is not a Codex-to-OKF "
                "bundle generated by this adapter"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    memories_dir = output_dir / "memories"
    memories_dir.mkdir()

    by_type: dict[str, list[PortableMemory]] = {}
    for memory in memories:
        by_type.setdefault(memory.memory_type, []).append(memory)

    root_links = []
    for memory_type, items in sorted(by_type.items()):
        type_dir = memories_dir / memory_type
        type_dir.mkdir()
        use_stacked = split == "type" or (
            split == "auto" and len(items) > DEFAULT_SPLIT_THRESHOLD
        )
        links = []
        if use_stacked:
            file_path = type_dir / f"{memory_type}.md"
            file_path.write_text(
                f"\n\n{ENTRY_DELIMITER}\n\n".join(
                    _render_okf(memory) for memory in items
                )
                + "\n",
                encoding="utf-8",
            )
            links.append((f"{len(items)} {memory_type} memories", file_path.name))
        else:
            used_slugs: Counter[str] = Counter()
            for memory in items:
                base_slug = _slugify(memory.title)
                used_slugs[base_slug] += 1
                suffix = (
                    f"-{used_slugs[base_slug]}" if used_slugs[base_slug] > 1 else ""
                )
                file_name = f"{base_slug}{suffix}.md"
                (type_dir / file_name).write_text(
                    _render_okf(memory) + "\n", encoding="utf-8"
                )
                links.append((memory.title, file_name))

        (type_dir / "index.md").write_text(
            _render_index(
                f"Codex {memory_type} memories",
                [(label, target) for label, target in links],
            ),
            encoding="utf-8",
        )
        root_links.append((f"{memory_type} ({len(items)})", f"{memory_type}/index.md"))

    (memories_dir / "index.md").write_text(
        _render_index("Codex memories", root_links), encoding="utf-8"
    )
    (output_dir / "index.md").write_text(
        _render_index(
            "Codex memory migration",
            [("Browse migrated memories", "memories/index.md")],
        ),
        encoding="utf-8",
    )
    (output_dir / "migration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _is_generated_bundle(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    marker = path / "migration_summary.json"
    if marker.is_symlink() or not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("adapter") == "codex-to-okf"


def _render_okf(memory: PortableMemory) -> str:
    lines = [
        "---",
        f"type: {_yaml(memory.memory_type)}",
        f"title: {_yaml(memory.title)}",
        f"description: {_yaml(memory.description)}",
        f"resource: {_yaml(memory.resource)}",
        f"tags: {_yaml(list(memory.tags))}",
    ]
    if memory.timestamp:
        lines.append(f"timestamp: {_yaml(memory.timestamp)}")
    lines.extend(
        (
            "x_memanto:",
            f"  type: {_yaml(memory.memory_type)}",
            "  confidence: 0.9",
            "  source: codex",
        )
    )
    for key, value in sorted(memory.metadata.items()):
        lines.append(f"{key}: {_yaml(value)}")
    lines.extend(("---", "", memory.body.strip()))
    return "\n".join(lines)


def _render_index(title: str, links: list[tuple[str, str]]) -> str:
    lines = (
        "---",
        "type: index",
        f"title: {_yaml(title)}",
        "---",
        "",
        f"# {title}",
        "",
    )
    return (
        "\n".join(lines)
        + "\n"
        + "\n".join(f"- [{label}]({target})" for label, target in links)
        + "\n"
    )


def _yaml(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if item)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return ()


def _tags(values: Iterable[str]) -> tuple[str, ...]:
    result = []
    seen = set()
    for value in values:
        tag = _slugify(str(value), max_chars=40)
        if not tag or tag in seen:
            continue
        result.append(tag)
        seen.add(tag)
        if len(result) == MAX_TAGS:
            break
    return tuple(result)


def _slugify(value: str, max_chars: int = 70) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = _NON_ALNUM_RE.sub("-", ascii_value).strip("-")[:max_chars].strip("-")
    if slug:
        return slug
    return f"memory-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def _first_meaningful_line(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate and candidate not in {"---"} and ":" not in candidate[:20]:
            return _truncate(candidate, MAX_TITLE_CHARS)
    return fallback


def _truncate(value: str, limit: int) -> str:
    normalized = _SPACE_RE.sub(" ", value).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _iso_timestamp(value: int | str | None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            try:
                return (
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                    .isoformat()
                )
            except ValueError:
                return None
    else:
        numeric = float(value)
    if numeric > 10_000_000_000:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_fingerprint(memories: Iterable[SourceMemory]) -> str:
    records = [asdict(memory) for memory in memories]
    records.sort(
        key=lambda record: json.dumps(
            record,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    canonical = json.dumps(
        records,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _load_source(
    source: Path,
    *,
    source_format: str,
    state_db: Path | None,
    strict: bool,
    stats: MigrationStats,
) -> tuple[list[SourceMemory], str]:
    resolved_format = source_format
    resolved_source = source
    if source_format == "auto":
        if source.is_dir():
            try:
                resolved_source = discover_memory_db(source)
                resolved_format = "memory-db"
            except FileNotFoundError:
                resolved_format = "sessions"
        elif source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            resolved_format = "memory-db"
        elif source.suffix.lower() == ".json":
            resolved_format = "export-json"
        else:
            resolved_format = "sessions"

    if resolved_format == "memory-db":
        companion = state_db or discover_state_db(resolved_source)
        memories = load_memory_database(resolved_source, companion)
        if source_format == "auto" and source.is_dir() and not memories:
            rollout_memories = load_session_rollouts(source, strict=strict, stats=stats)
            if rollout_memories:
                return rollout_memories, "sessions"
        return memories, resolved_format
    if resolved_format == "export-json":
        return load_source_export(resolved_source), resolved_format
    if resolved_format == "sessions":
        return (
            load_session_rollouts(resolved_source, strict=strict, stats=stats),
            resolved_format,
        )
    raise ValueError(f"Unsupported source format: {resolved_format}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Codex memories or rollout sessions to an OKF bundle."
    )
    parser.add_argument(
        "source",
        type=Path,
        help=(
            "Codex home, memories SQLite DB, exported JSON, rollout JSONL, "
            "or sessions directory"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("out/okf-bundle"),
        help="Destination OKF bundle (default: out/okf-bundle)",
    )
    parser.add_argument(
        "--source-format",
        choices=("auto", "memory-db", "export-json", "sessions"),
        default="auto",
    )
    parser.add_argument(
        "--state-db",
        type=Path,
        help="Optional Codex state DB for cwd, git, and CLI-version provenance",
    )
    parser.add_argument(
        "--split",
        choices=("auto", "file", "type"),
        default="file",
        help="OKF layout (default: file)",
    )
    parser.add_argument(
        "--export-source",
        type=Path,
        help="Also write a reviewable JSON snapshot of the source records",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail instead of skipping malformed rollout JSONL lines",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.source.exists():
        print(f"error: source not found: {args.source}", file=sys.stderr)
        return 2
    if args.state_db and not args.state_db.exists():
        print(f"error: state DB not found: {args.state_db}", file=sys.stderr)
        return 2

    stats = MigrationStats(source_format=args.source_format)
    source_redactor = Redactor()
    try:
        source_memories, resolved_format = _load_source(
            args.source,
            source_format=args.source_format,
            state_db=args.state_db,
            strict=args.strict,
            stats=stats,
        )
        stats.source_format = resolved_format
        safe_source_memories = [
            SourceMemory(
                **{
                    **asdict(memory),
                    "raw_memory": source_redactor.redact(memory.raw_memory),
                    "rollout_summary": source_redactor.redact(memory.rollout_summary),
                    "cwd": source_redactor.redact(memory.cwd) or None,
                    "rollout_path": source_redactor.redact(memory.rollout_path) or None,
                    "git_branch": source_redactor.redact(memory.git_branch) or None,
                    "thread_title": source_redactor.redact(memory.thread_title) or None,
                }
            )
            for memory in source_memories
        ]
        fingerprint = _source_fingerprint(safe_source_memories)
        mapping_redactor = Redactor()
        mapped = map_source_memories(
            safe_source_memories, redactor=mapping_redactor, stats=stats
        )
        stats.redactions.update(source_redactor.counts)
        if not mapped:
            raise ValueError(
                "No importable Codex memories were found. If the memory DB is "
                "empty, point --source-format sessions at ~/.codex/sessions."
            )
        summary = {
            "adapter": "codex-to-okf",
            "adapter_schema": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_fingerprint": fingerprint,
            **stats.as_dict(),
        }
        write_okf_bundle(
            mapped,
            args.output,
            split=args.split,
            overwrite=args.overwrite,
            summary=summary,
        )
        if args.export_source:
            write_source_export(
                safe_source_memories,
                args.export_source,
                source_fingerprint=fingerprint,
                codex_version=next(
                    (
                        memory.cli_version
                        for memory in safe_source_memories
                        if memory.cli_version
                    ),
                    None,
                ),
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Mapped {stats.source_records} Codex records into "
        f"{stats.mapped_memories} OKF memories at {args.output}"
    )
    print(
        "Types: "
        + ", ".join(
            f"{key}={value}" for key, value in sorted(stats.type_counts.items())
        )
    )
    print(
        "Redactions: "
        + (
            ", ".join(
                f"{key}={value}" for key, value in sorted(stats.redactions.items())
            )
            or "none"
        )
    )
    print(f"Source fingerprint: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

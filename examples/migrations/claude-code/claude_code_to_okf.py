#!/usr/bin/env python3
"""Migrate Claude Code's local project memory into a portable OKF bundle.

The adapter deliberately reads only user-owned, durable Claude Code state:

* ``projects/<project>/memory/*.md`` auto-memory documents
* ``history.jsonl`` user prompts for the selected project
* project transcript JSONL files, limited to user/assistant text blocks
* ``todos/*.json`` entries linked to sessions observed for the project

Tool payloads, telemetry, attachments, file-history snapshots, shell
environment captures, and pasted-content blobs are never imported. Every
selected field passes through a defensive redaction layer before it is written
to OKF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.app.services.okf_export_service import OkfExportService

ADAPTER_ID = "claude-code-to-okf"
DEFAULT_MAX_SESSION_CHARS = 8_000
DEFAULT_MAX_TRANSCRIPT_CHARS = 8_000
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_SPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CLAUDE_TYPE_TO_MEMANTO = {
    "feedback": "instruction",
    "user": "preference",
    "project": "fact",
    "reference": "artifact",
}

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        "api-token",
        re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b"),
        "[REDACTED_API_TOKEN]",
    ),
    (
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
        "Bearer [REDACTED]",
    ),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|"
            r"client[_-]?secret|password|passwd|secret)\b"
            r"(\s*[:=]\s*)"
            r"(?!\$\{?[A-Z_][A-Z0-9_]*\}?)([^\s,;`\"']{6,})"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        "email",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
)


@dataclass(frozen=True)
class SourceRecord:
    """One Claude Code source concept ready to become a Memanto memory."""

    source_id: str
    source_kind: str
    title: str
    content: str
    memory_type: str
    tags: tuple[str, ...]
    source_ref: str
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationStats:
    """Auditable counters for source selection, mapping, and redaction."""

    project: str
    source_records: int = 0
    mapped_memories: int = 0
    skipped_records: int = 0
    invalid_json_lines: int = 0
    source_by_kind: Counter[str] = field(default_factory=Counter)
    mapped_by_type: Counter[str] = field(default_factory=Counter)
    redactions: Counter[str] = field(default_factory=Counter)
    observed_session_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Return stable, JSON-serializable summary data."""
        return {
            "project": self.project,
            "source_records": self.source_records,
            "mapped_memories": self.mapped_memories,
            "skipped_records": self.skipped_records,
            "invalid_json_lines": self.invalid_json_lines,
            "source_by_kind": dict(sorted(self.source_by_kind.items())),
            "mapped_by_type": dict(sorted(self.mapped_by_type.items())),
            "redactions": dict(sorted(self.redactions.items())),
            "observed_sessions": len(self.observed_session_ids),
        }


class Redactor:
    """Remove machine-local paths, identifiers, and common secret shapes."""

    def __init__(self, home: Path, project: Path):
        self.home = str(home.expanduser().resolve())
        self.project = str(project.expanduser().resolve())
        self.counts: Counter[str] = Counter()

    def redact(self, value: str) -> str:
        """Return a redacted copy and accumulate replacement counts."""
        text = value
        replacements = (
            (self.project, "${PROJECT}", "project-path"),
            (self.home, "${HOME}", "home-path"),
        )
        for needle, replacement, label in replacements:
            if not needle:
                continue
            count = text.count(needle)
            if count:
                text = text.replace(needle, replacement)
                self.counts[label] += count

        for label, pattern, replacement in _SECRET_PATTERNS:
            text, count = pattern.subn(replacement, text)
            if count:
                self.counts[label] += count
        return text


def stable_id(*parts: str) -> str:
    """Return a deterministic, non-identifying source id."""
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def normalize_project(value: str | Path) -> str:
    """Normalize a project path for equality checks across trailing slashes."""
    return str(Path(str(value).strip()).expanduser().resolve())


def project_slug(project: str | Path) -> str:
    """Approximate Claude Code's path-derived project directory slug."""
    normalized = normalize_project(project)
    return re.sub(r"[^A-Za-z0-9_-]", "-", normalized)


def discover_project_dir(claude_home: Path, project: Path) -> Path:
    """Find the Claude Code project-state directory for ``project``.

    Claude Code has used a few subtly different path-slug encodings over time.
    Prefer an exact current slug, then fall back to a punctuation-insensitive
    comparison. Ambiguous matches are rejected instead of guessed.
    """
    projects_root = claude_home / "projects"
    exact = projects_root / project_slug(project)
    if exact.is_dir():
        return exact

    wanted = _SLUG_RE.sub("", normalize_project(project).lower())
    candidates = (
        [
            child
            for child in projects_root.iterdir()
            if child.is_dir() and _SLUG_RE.sub("", child.name.lower()) == wanted
        ]
        if projects_root.is_dir()
        else []
    )

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"No Claude Code project data found for {project}. "
            "Pass --project-data explicitly."
        )
    names = ", ".join(str(path) for path in candidates)
    raise RuntimeError(
        f"Multiple Claude Code project directories match {project}: {names}. "
        "Pass --project-data explicitly."
    )


def iter_jsonl(path: Path, stats: MigrationStats) -> Iterator[dict[str, Any]]:
    """Yield object records from JSONL while counting malformed lines."""
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                stats.invalid_json_lines += 1
                continue
            if isinstance(value, dict):
                yield value
            else:
                stats.skipped_records += 1


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split optional YAML frontmatter from a Markdown body."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, text[match.end() :].strip()


def title_from_text(text: str, limit: int = 80) -> str:
    """Create a compact one-line title from source text."""
    clean = _SPACE_RE.sub(" ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def epoch_ms_to_iso(value: Any) -> str | None:
    """Convert a Claude history millisecond timestamp to UTC ISO 8601."""
    try:
        stamp = float(value) / 1000
        return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def iso_timestamp(value: Any) -> str | None:
    """Normalize an ISO timestamp to an explicit timezone when possible."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def load_memory_documents(
    project_dir: Path,
    redactor: Redactor,
    stats: MigrationStats,
) -> list[SourceRecord]:
    """Load Claude Code auto-memory Markdown documents."""
    memory_dir = project_dir / "memory"
    if not memory_dir.is_dir():
        return []

    records: list[SourceRecord] = []
    for path in sorted(memory_dir.glob("*.md")):
        if path.name.lower() == "memory.md":
            continue
        stats.source_records += 1
        stats.source_by_kind["auto-memory"] += 1
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = split_frontmatter(raw)
        if not body:
            stats.skipped_records += 1
            continue

        claude_type = str(frontmatter.get("type") or path.stem.split("_", 1)[0]).lower()
        memory_type = _CLAUDE_TYPE_TO_MEMANTO.get(claude_type, "context")
        title = str(
            frontmatter.get("name")
            or frontmatter.get("title")
            or path.stem.replace("_", " ")
        )
        description = str(frontmatter.get("description") or "").strip()
        content = body
        if description and description.lower() not in body.lower():
            content = f"{description}\n\n{body}"

        source_id = stable_id("memory", path.name, body)
        records.append(
            SourceRecord(
                source_id=source_id,
                source_kind="auto-memory",
                title=redactor.redact(title),
                content=redactor.redact(content),
                memory_type=memory_type,
                tags=("claude-code", "auto-memory", claude_type),
                source_ref=f"claude-code:memory:{source_id}",
                metadata={
                    "claude_memory_type": claude_type,
                    "source_file": redactor.redact(str(path)),
                },
            )
        )
    return records


def load_history_sessions(
    history_path: Path,
    project: Path,
    redactor: Redactor,
    stats: MigrationStats,
    max_chars: int = DEFAULT_MAX_SESSION_CHARS,
) -> list[SourceRecord]:
    """Group global Claude Code prompt history by project session."""
    wanted = normalize_project(project)
    grouped: dict[str, list[tuple[str | None, str]]] = defaultdict(list)

    for row in iter_jsonl(history_path, stats):
        row_project = row.get("project")
        if not isinstance(row_project, str):
            stats.skipped_records += 1
            continue
        try:
            matches = normalize_project(row_project) == wanted
        except (OSError, ValueError):
            matches = row_project.strip() == str(project).strip()
        if not matches:
            continue

        stats.source_records += 1
        stats.source_by_kind["history-prompt"] += 1
        session_id = str(row.get("sessionId") or "").strip()
        display = row.get("display")
        if not session_id or not isinstance(display, str) or not display.strip():
            stats.skipped_records += 1
            continue

        prompt = display.strip()
        # Slash commands are client control traffic, not durable user context.
        if prompt.startswith("/") and "\n" not in prompt and " " not in prompt:
            stats.skipped_records += 1
            continue
        grouped[session_id].append((epoch_ms_to_iso(row.get("timestamp")), prompt))
        stats.observed_session_ids.add(session_id)

    records: list[SourceRecord] = []
    for session_id, prompts in sorted(grouped.items()):
        prompts.sort(key=lambda pair: pair[0] or "")
        sections = [
            f"## User prompt {index}\n\n{prompt}"
            for index, (_, prompt) in enumerate(prompts, start=1)
        ]
        content = "\n\n".join(sections)
        if len(content) > max_chars:
            content = (
                content[: max_chars - 80].rstrip()
                + f"\n\n[Truncated after {max_chars} characters by migration policy.]"
            )
        first_prompt = prompts[0][1]
        source_id = stable_id("history", session_id, first_prompt)
        records.append(
            SourceRecord(
                source_id=source_id,
                source_kind="history-session",
                title=redactor.redact(
                    f"Claude Code session: {title_from_text(first_prompt, 58)}"
                ),
                content=redactor.redact(content),
                memory_type="context",
                tags=("claude-code", "history", "user-prompts"),
                source_ref=f"claude-code:history:{source_id}",
                created_at=prompts[0][0],
                metadata={
                    "prompt_count": len(prompts),
                    "session_fingerprint": stable_id("session", session_id),
                },
            )
        )
    return records


def extract_message_text(message: Any) -> str:
    """Return only natural-language text from a Claude transcript message."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in (None, "text"):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks)


def load_transcripts(
    project_dir: Path,
    redactor: Redactor,
    stats: MigrationStats,
    max_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS,
    include_subagents: bool = False,
) -> list[SourceRecord]:
    """Load user/assistant text from persisted project transcripts."""
    patterns = (
        ("*.jsonl", "**/subagents/*.jsonl") if include_subagents else ("*.jsonl",)
    )
    paths = sorted({path for pattern in patterns for path in project_dir.glob(pattern)})
    records: list[SourceRecord] = []

    for path in paths:
        turns: list[tuple[str, str, str | None]] = []
        session_ids: set[str] = set()
        for row in iter_jsonl(path, stats):
            row_type = row.get("type")
            if row_type not in {"user", "assistant"}:
                continue
            text = extract_message_text(row.get("message"))
            if not text:
                continue
            stats.source_records += 1
            stats.source_by_kind["transcript-turn"] += 1
            session_id = str(row.get("sessionId") or path.stem)
            session_ids.add(session_id)
            stats.observed_session_ids.add(session_id)
            turns.append((str(row_type), text, iso_timestamp(row.get("timestamp"))))

        if not turns:
            continue
        sections = [
            f"## {role.title()} turn {index}\n\n{text}"
            for index, (role, text, _) in enumerate(turns, start=1)
        ]
        content = "\n\n".join(sections)
        if len(content) > max_chars:
            content = (
                content[: max_chars - 80].rstrip()
                + f"\n\n[Truncated after {max_chars} characters by migration policy.]"
            )
        source_id = stable_id("transcript", path.name, *sorted(session_ids))
        records.append(
            SourceRecord(
                source_id=source_id,
                source_kind="transcript",
                title=f"Claude Code transcript {source_id[:8]}",
                content=redactor.redact(content),
                memory_type="context",
                tags=("claude-code", "transcript", "conversation"),
                source_ref=f"claude-code:transcript:{source_id}",
                created_at=next((stamp for _, _, stamp in turns if stamp), None),
                metadata={
                    "turn_count": len(turns),
                    "source_file": redactor.redact(str(path)),
                    "includes_subagent": "subagents" in path.parts,
                },
            )
        )
    return records


def todo_session_id(path: Path) -> str:
    """Extract the owning session id from a Claude Code todo filename."""
    return path.name.split("-agent-", 1)[0]


def load_todos(
    claude_home: Path,
    redactor: Redactor,
    stats: MigrationStats,
) -> list[SourceRecord]:
    """Load todo items whose session belongs to the selected project."""
    todo_dir = claude_home / "todos"
    if not todo_dir.is_dir() or not stats.observed_session_ids:
        return []

    records: list[SourceRecord] = []
    for path in sorted(todo_dir.glob("*.json")):
        session_id = todo_session_id(path)
        if session_id not in stats.observed_session_ids:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stats.invalid_json_lines += 1
            continue
        if not isinstance(data, list):
            stats.skipped_records += 1
            continue

        for index, item in enumerate(data):
            stats.source_records += 1
            stats.source_by_kind["todo"] += 1
            if not isinstance(item, dict):
                stats.skipped_records += 1
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                stats.skipped_records += 1
                continue
            status = str(item.get("status") or "pending").lower()
            source_id = stable_id("todo", session_id, str(index), content)
            records.append(
                SourceRecord(
                    source_id=source_id,
                    source_kind="todo",
                    title=redactor.redact(title_from_text(content)),
                    content=redactor.redact(content.strip()),
                    memory_type="event" if status == "completed" else "commitment",
                    tags=("claude-code", "todo", f"status:{status}"),
                    source_ref=f"claude-code:todo:{source_id}",
                    metadata={
                        "status": status,
                        "active_form": redactor.redact(
                            str(item.get("activeForm") or "")
                        ),
                        "session_fingerprint": stable_id("session", session_id),
                    },
                )
            )
    return records


def deduplicate(
    records: Iterable[SourceRecord], stats: MigrationStats
) -> list[SourceRecord]:
    """Remove exact semantic duplicates while keeping first-source precedence."""
    seen: set[str] = set()
    unique: list[SourceRecord] = []
    for record in records:
        fingerprint = hashlib.sha256(
            f"{record.memory_type}\x1f{record.title}\x1f{record.content}".encode()
        ).hexdigest()
        if fingerprint in seen:
            stats.skipped_records += 1
            continue
        seen.add(fingerprint)
        unique.append(record)
    return unique


def collect_records(
    claude_home: Path,
    project: Path,
    project_dir: Path,
    *,
    include_history: bool = True,
    include_transcripts: bool = True,
    include_subagents: bool = False,
    include_todos: bool = True,
    max_session_chars: int = DEFAULT_MAX_SESSION_CHARS,
    max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS,
) -> tuple[list[SourceRecord], MigrationStats]:
    """Collect, redact, map, and summarize selected Claude Code state."""
    project = Path(normalize_project(project))
    stats = MigrationStats(project=project.name)
    redactor = Redactor(claude_home.parent, project)

    records: list[SourceRecord] = []
    records.extend(load_memory_documents(project_dir, redactor, stats))
    if include_history:
        records.extend(
            load_history_sessions(
                claude_home / "history.jsonl",
                project,
                redactor,
                stats,
                max_chars=max_session_chars,
            )
        )
    if include_transcripts:
        records.extend(
            load_transcripts(
                project_dir,
                redactor,
                stats,
                max_chars=max_transcript_chars,
                include_subagents=include_subagents,
            )
        )
    if include_todos:
        records.extend(load_todos(claude_home, redactor, stats))

    records = deduplicate(records, stats)
    stats.mapped_memories = len(records)
    stats.redactions.update(redactor.counts)
    for record in records:
        stats.mapped_by_type[record.memory_type] += 1
    return records, stats


def record_to_memanto(record: SourceRecord) -> dict[str, Any]:
    """Convert a source record to the shape accepted by OkfExportService."""
    supporting = [
        "",
        "---",
        "[Supporting data]",
        f"- Claude source kind: {record.source_kind}",
    ]
    for key, value in sorted(record.metadata.items()):
        if value not in (None, "", [], {}):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
            supporting.append(f"- {key}: {rendered}")
    content = record.content.rstrip() + "\n" + "\n".join(supporting)
    return {
        "id": record.source_id,
        "title": record.title,
        "content": content,
        "tags": list(record.tags),
        "confidence": 0.85 if record.source_kind == "auto-memory" else 0.75,
        "provenance": "imported",
        "source": "claude-code",
        "source_ref": record.source_ref,
        "status": "active",
        "created_at": record.created_at,
    }


def normalize_generated_markdown(output: Path) -> None:
    """Remove exporter padding so the committed bundle stays diff-clean."""
    for path in output.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        normalized = "\n".join(line.rstrip() for line in text.splitlines()).rstrip()
        path.write_text(normalized + "\n", encoding="utf-8")


def is_adapter_output(path: Path) -> bool:
    """Return whether ``path`` contains this adapter's summary marker."""
    summary_path = path / "migration_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return isinstance(summary, dict) and summary.get("adapter") == ADAPTER_ID


def paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either resolved path contains the other."""
    first = first.expanduser().resolve()
    second = second.expanduser().resolve()
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def write_okf_bundle(
    records: list[SourceRecord],
    stats: MigrationStats,
    output: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Write records through Memanto's shipped OKF exporter."""
    output = output.expanduser().resolve()
    if output.exists():
        if not force:
            raise FileExistsError(
                f"Output already exists: {output}. Pass --force to replace it."
            )
        if not output.is_dir() or not is_adapter_output(output):
            raise FileExistsError(
                f"Refusing to replace unrecognized output: {output}. "
                "Choose a new directory or remove it yourself after inspection."
            )
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record.memory_type].append(record_to_memanto(record))

    exporter = OkfExportService(exports_dir=output.parent / ".memanto-exports")
    result = exporter.write_okf_bundle(
        agent_id="claude-code-import",
        memories_by_type=dict(grouped),
        output_dir=output,
        split="file",
    )
    normalize_generated_markdown(output)
    summary = {
        "adapter": ADAPTER_ID,
        "schema_version": 1,
        **stats.to_dict(),
        "okf_output": {
            "total_memories": result["total_memories"],
            "per_type_counts": result["per_type_counts"],
            "sections": result["sections"],
        },
    }
    (output / "migration_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Claude Code project memory to a portable OKF bundle."
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=Path.home() / ".claude",
        help="Claude Code state directory (default: ~/.claude).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        required=True,
        help="Original project path used by Claude Code.",
    )
    parser.add_argument(
        "--project-data",
        type=Path,
        help="Explicit projects/<slug> directory; otherwise auto-discovered.",
    )
    parser.add_argument("--output", type=Path, required=True, help="OKF bundle path.")
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Exclude the global prompt history for this project.",
    )
    parser.add_argument(
        "--no-transcripts",
        action="store_true",
        help="Exclude persisted project transcripts.",
    )
    parser.add_argument(
        "--include-subagents",
        action="store_true",
        help="Include text-only subagent transcripts (off by default).",
    )
    parser.add_argument(
        "--no-todos",
        action="store_true",
        help="Exclude todo state linked to observed project sessions.",
    )
    parser.add_argument(
        "--max-session-chars",
        type=int,
        default=DEFAULT_MAX_SESSION_CHARS,
    )
    parser.add_argument(
        "--max-transcript-chars",
        type=int,
        default=DEFAULT_MAX_TRANSCRIPT_CHARS,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the Claude Code → OKF conversion."""
    args = parse_args(argv)
    claude_home = args.claude_home.expanduser().resolve()
    project = Path(normalize_project(args.project))
    project_dir = (
        args.project_data.expanduser().resolve()
        if args.project_data
        else discover_project_dir(claude_home, project)
    )
    output = args.output.expanduser().resolve()
    for source_path in (claude_home, project_dir):
        if paths_overlap(output, source_path):
            raise ValueError(
                f"Output {output} overlaps Claude Code source data at {source_path}."
            )

    records, stats = collect_records(
        claude_home,
        project,
        project_dir,
        include_history=not args.no_history,
        include_transcripts=not args.no_transcripts,
        include_subagents=args.include_subagents,
        include_todos=not args.no_todos,
        max_session_chars=args.max_session_chars,
        max_transcript_chars=args.max_transcript_chars,
    )
    if not records:
        raise RuntimeError(
            "No importable Claude Code memories were found for the selected project."
        )
    summary = write_okf_bundle(records, stats, output, force=args.force)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

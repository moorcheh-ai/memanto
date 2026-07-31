"""Privacy-first Codex JSONL to OKF conversion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_ROLES = {"user", "assistant"}
PRIVATE_BLOCK_RE = re.compile(
    r"<(?:bridge_context|bridge_instructions|environment_context)>.*?"
    r"</(?:bridge_context|bridge_instructions|environment_context)>",
    re.DOTALL,
)
USER_INPUT_RE = re.compile(r"<user_input>\s*(.*?)\s*</user_input>", re.DOTALL)
RESIDUAL_TRANSPORT_RE = re.compile(
    r"</?(?:bridge|lark)_[A-Za-z0-9_-]+(?:\s[^>]*)?>",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d[\d ()-]{7,}\d|1[3-9]\d[ -]?\d{4}[ -]?\d{4})(?!\d)"
)
OPEN_ID_RE = re.compile(r"\b(?:ou|oc|om)_[A-Za-z0-9_-]{8,}\b")
SECRET_RE = re.compile(r"(?i)\b(?:sk|gh[opusr]|xox[baprs]|AIza)[A-Za-z0-9_-]{12,}\b")
QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:sid|token|key|code|signature)=)[^&#\s]+")


@dataclass(frozen=True)
class ConversionResult:
    """Summary of a completed conversion."""

    input_records: int
    message_records: int
    exported_memories: int
    skipped_private: int
    redactions: int
    output_dir: Path


@dataclass(frozen=True)
class _Message:
    """Normalized conversation message selected from a rollout record."""

    timestamp: str
    role: str
    text: str
    source_line: int


def convert_session(
    source: Path,
    output_dir: Path,
    *,
    include_pattern: str | None = None,
    limit: int | None = None,
) -> ConversionResult:
    """Convert allowed Codex messages into a one-file-per-memory OKF bundle."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    messages, input_records = _read_messages(source)
    matcher = re.compile(include_pattern, re.IGNORECASE) if include_pattern else None

    selected: list[_Message] = []
    skipped_private = 0
    redactions = 0
    for message in messages:
        clean, count = redact_text(message.text)
        if not clean:
            skipped_private += 1
            continue
        if matcher and not matcher.search(clean):
            continue
        selected.append(
            _Message(
                timestamp=message.timestamp,
                role=message.role,
                text=clean,
                source_line=message.source_line,
            )
        )
        redactions += count
        if limit is not None and len(selected) >= limit:
            break

    _write_bundle(source, output_dir, selected)
    return ConversionResult(
        input_records=input_records,
        message_records=len(messages),
        exported_memories=len(selected),
        skipped_private=skipped_private,
        redactions=redactions,
        output_dir=output_dir.resolve(),
    )


def redact_text(text: str) -> tuple[str, int]:
    """Remove transport metadata and replace common identifiers and secrets."""
    original = text
    text = PRIVATE_BLOCK_RE.sub("", text)

    user_input = USER_INPUT_RE.search(text)
    if user_input:
        text = _decode_user_input(user_input.group(1))

    if RESIDUAL_TRANSPORT_RE.search(text):
        return "", 1

    substitutions = (
        (EMAIL_RE, "[REDACTED_EMAIL]"),
        (PHONE_RE, "[REDACTED_PHONE]"),
        (OPEN_ID_RE, "[REDACTED_BRIDGE_ID]"),
        (SECRET_RE, "[REDACTED_SECRET]"),
        (QUERY_SECRET_RE, r"\1[REDACTED]"),
    )
    count = 0
    for pattern, replacement in substitutions:
        text, replaced = pattern.subn(replacement, text)
        count += replaced

    text = text.strip()
    if not text:
        return "", count + (1 if original else 0)
    return text, count


def _read_messages(source: Path) -> tuple[list[_Message], int]:
    """Read valid message records from a Codex JSONL rollout."""
    messages: list[_Message] = []
    input_records = 0
    with source.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            input_records += 1
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            message = _extract_message(record, line_number)
            if message is not None:
                messages.append(message)
    return messages, input_records


def _extract_message(record: dict[str, Any], line_number: int) -> _Message | None:
    """Extract one allowed user or assistant message from a rollout record."""
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    role = payload.get("role")
    if role not in ALLOWED_ROLES:
        return None

    content = payload.get("content")
    if not isinstance(content, list):
        return None
    parts = list(_text_parts(content))
    if not parts:
        return None
    return _Message(
        timestamp=str(record.get("timestamp") or ""),
        role=role,
        text="\n\n".join(parts),
        source_line=line_number,
    )


def _text_parts(content: Iterable[Any]) -> Iterable[str]:
    """Yield non-empty textual parts from a message content array."""
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"input_text", "output_text", "text"}:
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            yield text.strip()


def _decode_user_input(value: str) -> str:
    """Decode a Bridge user_input JSON payload while tolerating plain text."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value.strip()
    if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
        return parsed["text"].strip()
    return value.strip()


def _write_bundle(source: Path, output_dir: Path, messages: list[_Message]) -> None:
    """Write selected messages and indexes as an OKF bundle."""
    memories_dir = output_dir / "memories" / "conversation"
    memories_dir.mkdir(parents=True, exist_ok=True)
    # This directory is owned by the adapter. Remove only its generated Markdown
    # files so rerunning with a smaller selection cannot leak stale memories.
    for previous in memories_dir.glob("*.md"):
        previous.unlink()

    source_fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    links: list[tuple[str, str]] = []
    for index, message in enumerate(messages, 1):
        filename = f"{index:03d}-{message.role}.md"
        title = f"Codex {message.role} message {index}"
        document = _okf_document(
            title=title,
            message=message,
            source_fingerprint=source_fingerprint,
        )
        (memories_dir / filename).write_text(document, encoding="utf-8")
        links.append((title, filename))

    index_lines = [
        "---",
        "type: index",
        'title: "Codex conversation memories"',
        "---",
        "",
        "# Codex conversation memories",
        "",
    ]
    index_lines.extend(f"- [{title}]({filename})" for title, filename in links)
    (memories_dir / "index.md").write_text(
        "\n".join(index_lines).rstrip() + "\n", encoding="utf-8"
    )

    root = [
        "---",
        "type: index",
        'title: "Codex session OKF export"',
        "---",
        "",
        "# Codex session OKF export",
        "",
        f"- Source fingerprint: `{source_fingerprint}`",
        f"- Exported memories: {len(messages)}",
        "- Privacy mode: transport metadata excluded; identifiers redacted",
        "- [Conversation memories](memories/conversation/index.md)",
        "",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.md").write_text("\n".join(root), encoding="utf-8")


def _okf_document(*, title: str, message: _Message, source_fingerprint: str) -> str:
    """Render one normalized message as an OKF Markdown document."""
    safe_title = json.dumps(title, ensure_ascii=False)
    safe_timestamp = json.dumps(message.timestamp, ensure_ascii=False)
    return (
        "---\n"
        "type: conversation\n"
        f"title: {safe_title}\n"
        f"timestamp: {safe_timestamp}\n"
        "tags:\n"
        "  - codex\n"
        "  - migration\n"
        f"  - role-{message.role}\n"
        "x_memanto:\n"
        "  type: context\n"
        "  source: codex-session-jsonl\n"
        f"  source_fingerprint: {source_fingerprint}\n"
        f"  source_line: {message.source_line}\n"
        f"  role: {message.role}\n"
        "  privacy_filtered: true\n"
        "---\n\n"
        f"{message.text}\n"
    )

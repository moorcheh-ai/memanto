#!/usr/bin/env python3
"""Convert persisted PydanticAI ``ModelMessage`` JSON into an OKF bundle.

The adapter consumes the JSON produced by ``RunResult.all_messages_json()`` or
``ModelMessagesTypeAdapter.dump_json(messages)``.  It deliberately does not
import PydanticAI: an archive remains portable even after the source framework
has been uninstalled.

Each source message becomes one human-readable OKF memory.  A canonical JSON
sidecar preserves the complete source object (including fields introduced by a
future PydanticAI release), while a deterministic manifest ties every emitted
file back to the original archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ADAPTER_NAME = "pydanticai-history-to-okf"
ADAPTER_VERSION = "1.0.0"
OKF_VERSION = "0.1"
SOURCE_LABEL = "pydantic-ai-message-history"
GENERATOR_MARKER = f"<!-- generated-by: {ADAPTER_NAME} -->"
ENTRY_DELIMITER = "<!-- okf-entry -->"

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "refresh_token",
    "secret",
}
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email",
        re.compile(
            r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{8,}\d)(?!\w)"),
    ),
)


class MigrationError(ValueError):
    """A user-facing source or output validation failure."""


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    message_index: int
    location_id: str
    severity: str


@dataclass(frozen=True)
class History:
    raw_bytes: bytes
    messages: tuple[dict[str, Any], ...]
    source_sha256: str
    canonical_sha256: str


@dataclass(frozen=True)
class RenderedMessage:
    title: str
    description: str
    body: str
    memory_type: str | None
    confidence: float
    provenance: str
    part_kinds: tuple[str, ...]
    omitted_part_kinds: tuple[str, ...]


def canonical_json(value: Any) -> bytes:
    """Return the stable UTF-8 representation used by hashes and sidecars."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_non_finite(constant: str) -> None:
    raise MigrationError(f"non-finite JSON number is not supported: {constant}")


def load_history(path: str | Path) -> History:
    """Load and structurally validate a PydanticAI message-history export."""
    source_path = Path(path)
    try:
        raw = source_path.read_bytes()
    except OSError as exc:
        raise MigrationError(f"cannot read source history: {source_path}") from exc
    try:
        data = json.loads(
            raw.decode("utf-8-sig"),
            parse_constant=_reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("source history must be a UTF-8 JSON array") from exc
    if not isinstance(data, list):
        raise MigrationError("source history must be a JSON array")
    if not data:
        raise MigrationError("source history must contain at least one message")

    messages: list[dict[str, Any]] = []
    for index, message in enumerate(data):
        if not isinstance(message, dict):
            raise MigrationError(f"message {index}: expected an object")
        kind = message.get("kind")
        if kind not in {"request", "response"}:
            raise MigrationError(
                f"message {index}: unsupported kind {kind!r}; expected request or response"
            )
        parts = message.get("parts")
        if not isinstance(parts, list):
            raise MigrationError(f"message {index}: parts must be an array")
        for part_index, part in enumerate(parts):
            if not isinstance(part, dict):
                raise MigrationError(
                    f"message {index}, part {part_index}: expected an object"
                )
            if not isinstance(part.get("part_kind"), str):
                raise MigrationError(
                    f"message {index}, part {part_index}: part_kind must be a string"
                )
        messages.append(message)

    return History(
        raw_bytes=raw,
        messages=tuple(messages),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        canonical_sha256=hashlib.sha256(canonical_json(messages)).hexdigest(),
    )


def scan_history(messages: tuple[dict[str, Any], ...]) -> list[Finding]:
    """Find likely secrets and PII without putting matched values in the report."""
    findings: list[Finding] = []
    seen: set[tuple[str, str, int]] = set()

    def add_finding(
        category: str, path: str, message_index: int, severity: str
    ) -> None:
        identity = (category, path, message_index)
        if identity in seen:
            return
        seen.add(identity)
        # Hash only public location metadata, never the detected value.  Even a
        # truncated value hash can help an attacker guess low-entropy PII.
        location = f"{category}:{path}:{message_index}"
        findings.append(
            Finding(
                category=category,
                path=path,
                message_index=message_index,
                location_id=hashlib.sha256(location.encode("utf-8")).hexdigest()[:12],
                severity=severity,
            )
        )

    def visit(value: Any, path: str, message_index: int) -> None:
        if isinstance(value, dict):
            for key_index, (key, item) in enumerate(value.items()):
                key_text = str(key)
                key_findings: list[tuple[str, str]] = []
                for category, pattern in _SECRET_PATTERNS:
                    if pattern.search(key_text):
                        key_findings.append((category, "secret"))
                for category, pattern in _PII_PATTERNS:
                    if pattern.search(key_text):
                        key_findings.append((category, "pii"))

                item_path = (
                    f"{path}.<redacted-key:{key_index}>"
                    if key_findings
                    else f"{path}.{key_text}"
                )
                for category, severity in key_findings:
                    add_finding(category, item_path, message_index, severity)

                normalized_key = re.sub(r"[^a-z0-9]+", "_", key_text.casefold()).strip(
                    "_"
                )
                if (
                    normalized_key in _SENSITIVE_KEYS
                    and item is not None
                    and (not isinstance(item, str) or item.strip())
                ):
                    add_finding(
                        "named_secret_field", item_path, message_index, "secret"
                    )
                visit(item, item_path, message_index)
        elif isinstance(value, list):
            for item_index, item in enumerate(value):
                visit(item, f"{path}[{item_index}]", message_index)
        elif isinstance(value, str):
            for category, pattern in _SECRET_PATTERNS:
                for _match in pattern.finditer(value):
                    add_finding(category, path, message_index, "secret")
            for category, pattern in _PII_PATTERNS:
                for _match in pattern.finditer(value):
                    add_finding(category, path, message_index, "pii")

    for index, message in enumerate(messages):
        visit(message, f"messages[{index}]", index)
    return findings


def redact_history(
    messages: tuple[dict[str, Any], ...],
) -> tuple[tuple[dict[str, Any], ...], int]:
    """Return a JSON-only deep copy with known secrets and PII redacted."""
    replacements = 0

    def redact(value: Any) -> Any:
        nonlocal replacements
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key_index, (key, item) in enumerate(value.items()):
                key_text = str(key)
                key_categories = [
                    category
                    for category, pattern in (*_SECRET_PATTERNS, *_PII_PATTERNS)
                    if pattern.search(key_text)
                ]
                output_key = key_text
                if key_categories:
                    output_key = f"[REDACTED:{key_categories[0]}_key:{key_index}]"
                    while output_key in redacted:
                        output_key += "_"
                    replacements += 1

                normalized_key = re.sub(r"[^a-z0-9]+", "_", key_text.casefold()).strip(
                    "_"
                )
                if (
                    normalized_key in _SENSITIVE_KEYS
                    and item is not None
                    and (not isinstance(item, str) or item.strip())
                ):
                    redacted[output_key] = "[REDACTED:named_secret_field]"
                    replacements += 1
                else:
                    redacted[output_key] = redact(item)
            return redacted
        if isinstance(value, list):
            return [redact(item) for item in value]
        if not isinstance(value, str):
            return value
        result = value
        for category, pattern in (*_SECRET_PATTERNS, *_PII_PATTERNS):
            result, count = pattern.subn(f"[REDACTED:{category}]", result)
            replacements += count
        return result

    return tuple(redact(message) for message in messages), replacements


def _normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _single_line(value: str) -> str:
    return " ".join(value.replace("\r", "\n").splitlines()).strip()


def _markdown_text(value: Any) -> str:
    """Render PydanticAI content without silently Python-stringifying objects."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return json.dumps(value, allow_nan=False, ensure_ascii=False)
    if isinstance(value, list):
        blocks: list[str] = []
        for item in value:
            if isinstance(item, str):
                blocks.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    blocks.append(text)
                else:
                    blocks.append(_json_fence(item))
            else:
                blocks.append(_json_fence(item))
        return "\n\n".join(blocks)
    return _json_fence(value)


def _json_fence(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    longest = max((len(run) for run in re.findall(r"`+", payload)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}json\n{payload}\n{fence}"


def _escape_loader_delimiter(text: str) -> str:
    return text.replace(ENTRY_DELIMITER, "<!-- okf-entry-escaped -->")


def _plain_title_seed(part: dict[str, Any], heading: str) -> str:
    """Return title-safe text without rendering structured content as Markdown."""
    kind = str(part.get("part_kind") or "unknown")
    if kind in {"tool-call", "tool-return"}:
        return heading

    content = part.get("content")
    if isinstance(content, str):
        return _single_line(content)
    if isinstance(content, list):
        text_items: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_items.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    text_items.append(text)
        if text_items:
            return _single_line(" ".join(text_items))
    return heading


def _part_heading(part: dict[str, Any]) -> tuple[str, str, bool]:
    kind = str(part.get("part_kind") or "unknown")
    if kind == "system-prompt":
        return "System instruction", _markdown_text(part.get("content")), False
    if kind == "user-prompt":
        return "User", _markdown_text(part.get("content")), False
    if kind == "text":
        return "Assistant", _markdown_text(part.get("content")), False
    if kind == "tool-call":
        name = str(part.get("tool_name") or "unknown")
        detail = [
            f"Call ID: `{part.get('tool_call_id') or 'unknown'}`",
            "",
            "Arguments:",
        ]
        detail.append(_json_fence(part.get("args")))
        return f"Tool call · {name}", "\n".join(detail), False
    if kind == "tool-return":
        name = str(part.get("tool_name") or "unknown")
        detail = [
            f"Call ID: `{part.get('tool_call_id') or 'unknown'}`",
            f"Outcome: `{part.get('outcome') or 'unknown'}`",
            "",
            "Result:",
            _markdown_text(part.get("content")),
        ]
        return f"Tool result · {name}", "\n".join(detail), False
    if kind == "retry-prompt":
        return "Retry or validation error", _markdown_text(part.get("content")), False
    if kind in {"thinking", "builtin-tool-call", "builtin-tool-return"}:
        return kind, "", True
    return (
        f"Unsupported part · {kind}",
        "The complete source object is preserved in the JSON sidecar.",
        True,
    )


def render_message(message: dict[str, Any], index: int) -> RenderedMessage:
    """Create the human-facing representation of one source message."""
    parts = message.get("parts") or []
    sections: list[str] = []
    part_kinds: list[str] = []
    omitted: list[str] = []
    title_seed = ""

    for part in parts:
        kind = str(part.get("part_kind") or "unknown")
        part_kinds.append(kind)
        heading, text, is_omitted = _part_heading(part)
        if is_omitted:
            omitted.append(kind)
            sections.append(
                f"## {heading}\n\n> Hidden or non-text payload omitted from the "
                "human-readable body; the canonical source sidecar preserves it."
            )
            continue
        clean = _escape_loader_delimiter(text.strip())
        sections.append(f"## {heading}\n\n{clean}".rstrip())
        if not title_seed:
            title_seed = _escape_loader_delimiter(_plain_title_seed(part, heading))

    kind = str(message.get("kind"))
    if not title_seed:
        title_seed = ", ".join(part_kinds) or "empty message"
    role = "Request" if kind == "request" else "Response"
    title = f"{role} {index + 1:03d} · {title_seed[:70]}".rstrip()
    description = title_seed[:200]

    part_set = set(part_kinds)
    memory_type: str | None = None
    confidence = 0.8
    provenance = "observed"
    if part_set and part_set <= {"system-prompt"}:
        memory_type = "instruction"
        confidence = 0.95
        provenance = "explicit_statement"
    elif "retry-prompt" in part_set:
        memory_type = "error"
        confidence = 0.9
    elif part_set and part_set <= {"tool-call", "tool-return"}:
        memory_type = "artifact"
        confidence = 0.9
    elif "user-prompt" in part_set:
        confidence = 0.95
        provenance = "explicit_statement"
    elif "text" in part_set:
        confidence = 0.75

    metadata = [
        f"- Message index: `{index}`",
        f"- Kind: `{kind}`",
        f"- Run ID: `{message.get('run_id') or 'unknown'}`",
        f"- Conversation ID: `{message.get('conversation_id') or 'unknown'}`",
    ]
    body = "\n\n".join(sections)
    body += "\n\n---\n\n**Source metadata**\n\n" + "\n".join(metadata)
    return RenderedMessage(
        title=title,
        description=description,
        body=body.strip(),
        memory_type=memory_type,
        confidence=confidence,
        provenance=provenance,
        part_kinds=tuple(part_kinds),
        omitted_part_kinds=tuple(omitted),
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:72].rstrip("-") or "message"


def _yaml(value: Any) -> str:
    """JSON values are valid YAML and avoid a dependency in this adapter."""
    return json.dumps(value, allow_nan=False, ensure_ascii=False)


def _message_doc(
    message: dict[str, Any],
    index: int,
    rendered: RenderedMessage,
    sidecar_path: str,
    sidecar_sha256: str,
) -> str:
    kind = str(message["kind"])
    timestamp = _normalize_timestamp(message.get("timestamp"))
    if timestamp is None:
        for part in message.get("parts") or []:
            timestamp = _normalize_timestamp(part.get("timestamp"))
            if timestamp:
                break
    conversation_id = str(message.get("conversation_id") or "unknown")
    run_id = str(message.get("run_id") or "unknown")
    resource = (
        "pydantic-ai://conversations/"
        + quote(conversation_id, safe="")
        + "/runs/"
        + quote(run_id, safe="")
        + f"/messages/{index}"
    )
    tags = [
        "pydantic-ai",
        f"message:{kind}",
        f"conversation:{conversation_id}",
        f"run:{run_id}",
        *(f"part:{part_kind}" for part_kind in sorted(set(rendered.part_kinds))),
    ]
    lines = [
        "---",
        f"type: {_yaml('PydanticAI ' + kind)}",
        f"title: {_yaml(rendered.title)}",
        f"description: {_yaml(rendered.description)}",
        f"resource: {_yaml(resource)}",
        f"tags: {_yaml(tags)}",
    ]
    if timestamp:
        lines.append(f"timestamp: {_yaml(timestamp)}")
    lines.extend(
        [
            "x_memanto:",
            f"  source: {_yaml(SOURCE_LABEL)}",
            f"  confidence: {rendered.confidence}",
            f"  provenance: {_yaml(rendered.provenance)}",
        ]
    )
    if rendered.memory_type:
        lines.append(f"  type: {_yaml(rendered.memory_type)}")
    lines.extend(
        [
            "pydantic_ai:",
            "  schema_version: 1",
            f"  message_index: {index}",
            f"  message_kind: {_yaml(kind)}",
            f"  conversation_id: {_yaml(conversation_id)}",
            f"  run_id: {_yaml(run_id)}",
            f"  model_name: {_yaml(message.get('model_name'))}",
            f"  provider_name: {_yaml(message.get('provider_name'))}",
            f"  source_sidecar: {_yaml(sidecar_path)}",
            f"  source_sidecar_sha256: {_yaml(sidecar_sha256)}",
            f"  omitted_part_kinds: {_yaml(list(rendered.omitted_part_kinds))}",
            "---",
            "",
            f"# {rendered.title}",
            "",
            rendered.body,
            "",
        ]
    )
    return "\n".join(lines)


def _prepare_output(output: Path, force: bool) -> None:
    if output.is_symlink():
        raise MigrationError(f"refusing to write through output symlink: {output}")
    if output.exists() and not output.is_dir():
        raise MigrationError(f"output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        marker_path = output / "index.md"
        marker = marker_path.read_text("utf-8") if marker_path.is_file() else ""
        if GENERATOR_MARKER not in marker:
            raise MigrationError(
                f"refusing to overwrite non-adapter directory: {output}"
            )
        if not force:
            raise MigrationError(
                f"output already exists: {output}; pass --force to replace it"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)


def _write_index(output: Path, files: list[tuple[str, str]], source_count: int) -> None:
    lines = [
        GENERATOR_MARKER,
        "---",
        "type: index",
        f"title: {_yaml('PydanticAI portable message history')}",
        f"okf_version: {_yaml(OKF_VERSION)}",
        "---",
        "",
        "# PydanticAI message history — portable OKF",
        "",
        f"> {source_count} framework-generated messages, one readable memory per message.",
        "",
        "The complete canonical source is preserved under `source/`; the files below are",
        "the human-readable, Memanto-importable view.",
        "",
        "## Memories",
        "",
    ]
    lines.extend(f"- [{title}]({path})" for title, path in files)
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "- [`migration-manifest.json`](migration-manifest.json)",
            "- [`metrics/migration-report.json`](metrics/migration-report.json)",
            "- [`source/history.json`](source/history.json)",
            "",
        ]
    )
    (output / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _file_hashes(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "migration-manifest.json"
    }


def migrate(
    source: str | Path,
    output: str | Path,
    *,
    force: bool = False,
    allow_sensitive: bool = False,
    redact: bool = False,
) -> dict[str, Any]:
    """Convert *source* and return the machine-readable migration report."""
    if allow_sensitive and redact:
        raise MigrationError("--allow-sensitive and --redact are mutually exclusive")
    history = load_history(source)
    findings = scan_history(history.messages)
    if findings and not (allow_sensitive or redact):
        categories = ", ".join(sorted({finding.category for finding in findings}))
        raise MigrationError(
            "sensitive values detected ("
            + categories
            + "); sanitize the source, pass --redact, or explicitly pass "
            "--allow-sensitive"
        )

    messages = history.messages
    redaction_count = 0
    if redact:
        messages, redaction_count = redact_history(messages)

    output_path = Path(output)
    _prepare_output(output_path, force)
    memories_root = output_path / "memories"
    sidecars_root = output_path / "source" / "messages"
    metrics_root = output_path / "metrics"
    memories_root.mkdir(parents=True)
    sidecars_root.mkdir(parents=True)
    metrics_root.mkdir(parents=True)

    links: list[tuple[str, str]] = []
    kind_counts: Counter[str] = Counter()
    part_counts: Counter[str] = Counter()
    omitted_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    for index, message in enumerate(messages):
        rendered = render_message(message, index)
        kind = str(message["kind"])
        kind_counts[kind] += 1
        part_counts.update(rendered.part_kinds)
        omitted_counts.update(rendered.omitted_part_kinds)
        type_counts[rendered.memory_type or "auto"] += 1

        sidecar_rel = f"source/messages/{index:04d}.json"
        sidecar_bytes = canonical_json(message)
        sidecar = output_path / sidecar_rel
        sidecar.write_bytes(sidecar_bytes + b"\n")
        sidecar_sha = hashlib.sha256(sidecar_bytes).hexdigest()

        kind_dir = memories_root / kind
        kind_dir.mkdir(exist_ok=True)
        filename = f"{index:04d}-{_slug(rendered.title)}.md"
        relative = f"memories/{kind}/{filename}"
        doc = _message_doc(
            message,
            index,
            rendered,
            sidecar_rel,
            sidecar_sha,
        )
        (output_path / relative).write_text(doc, encoding="utf-8")
        links.append((rendered.title, relative))

    source_bytes = (
        json.dumps(
            list(messages), allow_nan=False, ensure_ascii=False, indent=2
        ).encode("utf-8")
        + b"\n"
        if redact
        else history.raw_bytes
    )
    (output_path / "source" / "history.json").write_bytes(source_bytes)
    _write_index(output_path, links, len(messages))

    report: dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "okf_version": OKF_VERSION,
        # Local absolute paths can disclose workstation details when evidence is
        # committed.  The content hash is the durable source identifier.
        "source_filename": Path(source).name,
        "source_sha256": history.source_sha256,
        "source_canonical_sha256": history.canonical_sha256,
        "output_canonical_sha256": hashlib.sha256(canonical_json(messages)).hexdigest(),
        "lossless": not redact,
        "source_messages": len(history.messages),
        "mapped_memories": len(messages),
        "skipped_messages": 0,
        "message_kind_counts": dict(sorted(kind_counts.items())),
        "part_kind_counts": dict(sorted(part_counts.items())),
        "omitted_human_readable_part_counts": dict(sorted(omitted_counts.items())),
        "memanto_type_counts": dict(sorted(type_counts.items())),
        "privacy": {
            "findings": [finding.__dict__ for finding in findings],
            "finding_count": len(findings),
            "redaction_count": redaction_count,
            "mode": "redact"
            if redact
            else "allow"
            if allow_sensitive
            else "fail-closed",
        },
    }
    (metrics_root / "migration-report.json").write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        **report,
        "files": _file_hashes(output_path),
    }
    (output_path / "migration-manifest.json").write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert PydanticAI ModelMessage JSON to a portable OKF bundle."
    )
    parser.add_argument("source", type=Path, help="PydanticAI message-history JSON")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    privacy = parser.add_mutually_exclusive_group()
    privacy.add_argument(
        "--allow-sensitive",
        action="store_true",
        help="Acknowledge and retain detected secrets or PII.",
    )
    privacy.add_argument(
        "--redact",
        action="store_true",
        help="Redact detected secrets and PII (the report marks output non-lossless).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = migrate(
            args.source,
            args.output,
            force=args.force,
            allow_sensitive=args.allow_sensitive,
            redact=args.redact,
        )
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Source messages : {report['source_messages']}")
    print(f"Mapped memories : {report['mapped_memories']}")
    print(f"Skipped messages: {report['skipped_messages']}")
    print(f"Type breakdown  : {report['memanto_type_counts']}")
    print(f"Lossless        : {report['lossless']}")
    print(f"OKF bundle      : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export real Codex CLI rollout messages to a privacy-safe OKF bundle.

The adapter intentionally reads only user/assistant conversation messages. It
never exports reasoning, tool calls, tool outputs, developer instructions, or
embedded images. Every exported entry carries a hash of its source envelope so
the included validator can prove provenance without publishing the raw rollout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADAPTER_VERSION = "0.1.0"
OKF_TYPE = "Codex CLI Conversation"
BUNDLE_ADAPTER = "codex-cli-sessions-to-okf"

INTERNAL_MESSAGE_RE = re.compile(
    r"<(?:codex_internal_context|environment_context|permissions instructions)\b",
    re.IGNORECASE,
)

# A single specification keeps redaction and the fail-closed privacy gate in
# sync. The gate intentionally uses a stricter OpenAI-key boundary than the
# replacement rule, while every other category shares the same pattern.
# Order matters: redact assignment lines before matching individual token shapes.
PRIVACY_RULE_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "secret_assignment",
        r"(?im)^.*(?:api[_ -]?key|access[_ -]?token|password|private[_ -]?key)"
        r"\s*(?::|=).*$",
        r"(?im)^.*(?:api[_ -]?key|access[_ -]?token|password|private[_ -]?key)"
        r"\s*(?::|=).*$",
    ),
    (
        "openai_key",
        r"(?i)\bsk-[A-Za-z0-9_-]{12,120}",
        r"(?i)\bsk-[A-Za-z0-9_-]{12,}\b",
    ),
    (
        "github_token",
        r"(?i)\bgh[opusr]_[A-Za-z0-9]{20,}\b",
        r"(?i)\bgh[opusr]_[A-Za-z0-9]{20,}\b",
    ),
    (
        "jwt",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
        r"[A-Za-z0-9_-]{8,}\b",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
        r"[A-Za-z0-9_-]{8,}\b",
    ),
    (
        "email",
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    ),
    (
        "phone",
        r"(?<!\w)(?:\+?\d[\s().-]*){9,15}(?!\w)",
        r"(?<!\w)(?:\+?\d[\s().-]*){9,15}(?!\w)",
    ),
    (
        "private_url_parameter",
        r"(?i)([?&](?:token|key|secret|auth|signature)=)[^&\s)]+",
        r"(?i)([?&](?:token|key|secret|auth|signature)=)[^&\s)]+",
    ),
    (
        "user_home",
        r"(?i)(?:[A-Z]:\\Users\\|/home/)[^\\/\s]+",
        r"(?i)(?:[A-Z]:\\Users\\|/home/)[^\\/\s]+",
    ),
    # Solana addresses and similar long base58 account identifiers. Hex digests
    # are intentionally left intact because they are useful provenance evidence.
    (
        "base58_account",
        r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])",
    ),
    (
        "credential_transfer_instruction",
        r"(?is)\b(?:send|share|paste|env[ií]a(?:me)?|comparte)\b"
        r"[^.\n]{0,160}\b(?:credentials?|private\s+keys?|api\s*keys?|secrets?|"
        r"credenciales?|claves?\s+privadas?|tokens?)\b[^.\n]*[.!]?",
        r"(?is)\b(?:send|share|paste|env[ií]a(?:me)?|comparte)\b"
        r"[^.\n]{0,160}\b(?:credentials?|private\s+keys?|api\s*keys?|secrets?|"
        r"credenciales?|claves?\s+privadas?|tokens?)\b[^.\n]*[.!]?",
    ),
)

REDACTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(redaction_pattern))
    for name, redaction_pattern, _ in PRIVACY_RULE_SPECS
)
PRIVACY_GATE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(gate_pattern)) for name, _, gate_pattern in PRIVACY_RULE_SPECS
)


@dataclass(frozen=True)
class MessageRecord:
    """One eligible public conversation message and its source provenance."""

    line_number: int
    timestamp: str
    session_id: str
    role: str
    text: str
    source_record_sha256: str


@dataclass(frozen=True)
class ExportedRecord:
    """One privacy-redacted message prepared for OKF rendering."""

    record: MessageRecord
    entry_id: str
    title: str
    redacted_text: str
    content_sha256: str
    redactions: dict[str, int]


@dataclass
class ParseStats:
    """Counts source records deliberately skipped during JSONL parsing."""

    unparseable_lines: int = 0


def _sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest for bytes."""
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    """Return a lowercase SHA-256 digest for UTF-8 text."""
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    """Stream a file into SHA-256 without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_envelope_hash(
    session_id: str, line_number: int, timestamp: str, role: str, text: str
) -> str:
    """Hash the canonical source envelope used as the provenance identity."""
    envelope = {
        "line_number": line_number,
        "role": role,
        "session_id": session_id,
        "text": text,
        "timestamp": timestamp,
    }
    canonical = json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _sha256_text(canonical)


def _message_text(payload: dict[str, Any]) -> str:
    """Extract only public text blocks from a rollout message payload."""
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return ""
    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in {"input_text", "output_text"}:
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return "\n\n".join(texts).strip()


def iter_message_records(
    source: Path, stats: ParseStats | None = None
) -> Iterable[MessageRecord]:
    """Yield public conversation messages from a Codex rollout JSONL file."""
    parse_stats = stats if stats is not None else ParseStats()
    current_session_id = "unknown"
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError:
                parse_stats.unparseable_lines += 1
                continue
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            if item.get("type") == "session_meta" and isinstance(payload, dict):
                candidate = payload.get("session_id") or payload.get("id")
                if isinstance(candidate, str) and candidate:
                    current_session_id = candidate
                continue
            if item.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = _message_text(payload)
            if not text or INTERNAL_MESSAGE_RE.search(text):
                continue
            timestamp = str(item.get("timestamp") or "")
            yield MessageRecord(
                line_number=line_number,
                timestamp=timestamp,
                session_id=current_session_id,
                role=role,
                text=text,
                source_record_sha256=_source_envelope_hash(
                    current_session_id, line_number, timestamp, role, text
                ),
            )


def redact_text(text: str, literals: Sequence[str] = ()) -> tuple[str, dict[str, int]]:
    """Return deterministic redacted text and per-rule replacement counts."""
    redacted = text
    counts: Counter[str] = Counter()
    for literal in sorted({v for v in literals if v}, key=len, reverse=True):
        redacted, count = re.subn(
            re.escape(literal), "[REDACTED_LITERAL]", redacted, flags=re.I
        )
        if count:
            counts["literal"] += count
    replacements = {
        "secret_assignment": "[REDACTED_SECRET_ASSIGNMENT]",
        "openai_key": "[REDACTED_OPENAI_KEY]",
        "github_token": "[REDACTED_GITHUB_TOKEN]",
        "jwt": "[REDACTED_JWT]",
        "email": "[REDACTED_EMAIL]",
        "phone": "[REDACTED_PHONE]",
        "private_url_parameter": r"\1[REDACTED]",
        "user_home": "[USER_HOME]",
        "base58_account": "[REDACTED_ACCOUNT]",
        "credential_transfer_instruction": (
            "[SAFETY_SUMMARY: Private credentials must remain confidential and "
            "must not be sent or shared.]"
        ),
    }
    for name, pattern in REDACTION_RULES:
        redacted, count = pattern.subn(replacements[name], redacted)
        if count:
            counts[name] += count
    return redacted.strip(), dict(sorted(counts.items()))


def privacy_findings(text: str) -> list[str]:
    """Return privacy-rule names still present in published message text."""
    return [name for name, pattern in PRIVACY_GATE_RULES if pattern.search(text)]


def select_records(
    records: Iterable[MessageRecord],
    *,
    roles: set[str],
    include: re.Pattern[str] | None,
    exclude: re.Pattern[str] | None,
    max_records: int,
    take: str,
) -> list[MessageRecord]:
    """Apply role, regex, ordering, and count selection deterministically."""
    selected = [
        record
        for record in records
        if record.role in roles
        and (include is None or include.search(record.text))
        and (exclude is None or not exclude.search(record.text))
    ]
    if max_records > 0 and len(selected) > max_records:
        selected = (
            selected[:max_records] if take == "first" else selected[-max_records:]
        )
    return selected


def _safe_timestamp(value: str) -> str:
    """Return a source timestamp or a valid UTC fallback."""
    if not value:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _json_yaml(value: Any) -> str:
    """JSON scalars/lists are valid YAML and avoid handwritten escaping bugs."""
    return json.dumps(value, ensure_ascii=False)


def _render_entry(item: ExportedRecord) -> str:
    """Render one exported record as an OKF-compatible Markdown document."""
    record = item.record
    tags = ["codex-cli", "conversation", record.role, "privacy-redacted"]
    session_ref = _sha256_text(record.session_id)[:16]
    frontmatter = [
        "---",
        f"type: {_json_yaml(OKF_TYPE)}",
        f"title: {_json_yaml(item.title)}",
        "description: "
        + _json_yaml(
            "A privacy-redacted conversational memory from a real Codex CLI run."
        ),
        f"resource: {_json_yaml(f'codex://session/{session_ref}#line-{record.line_number}')}",
        f"tags: {_json_yaml(tags)}",
        f"timestamp: {_json_yaml(_safe_timestamp(record.timestamp))}",
        f"source_tool: {_json_yaml('codex-cli')}",
        f"source_role: {_json_yaml(record.role)}",
        f"source_line: {record.line_number}",
        f"source_record_sha256: {_json_yaml(record.source_record_sha256)}",
        f"content_sha256: {_json_yaml(item.content_sha256)}",
        f"redaction_count: {sum(item.redactions.values())}",
        "---",
        "",
        f"# {item.title}",
        "",
        item.redacted_text,
        "",
    ]
    return "\n".join(frontmatter)


def _slug(item: ExportedRecord) -> str:
    """Build a stable chronological filename for an exported record."""
    stamp = re.sub(r"[^0-9]", "", item.record.timestamp)[:14] or "undated"
    return f"{stamp}-{item.record.role}-{item.entry_id}.md"


def _build_exported(
    records: Sequence[MessageRecord], literals: Sequence[str]
) -> list[ExportedRecord]:
    """Redact selected records and fail closed before any output is created."""
    exported: list[ExportedRecord] = []
    for index, record in enumerate(records, start=1):
        redacted, counts = redact_text(record.text, literals)
        findings = privacy_findings(redacted)
        if findings:
            raise ValueError(
                f"privacy gate rejected source line {record.line_number}: "
                + ", ".join(findings)
            )
        entry_id = record.source_record_sha256[:16]
        title = f"Codex {record.role} memory {index:03d}"
        exported.append(
            ExportedRecord(
                record=record,
                entry_id=entry_id,
                title=title,
                redacted_text=redacted,
                content_sha256=_sha256_text(redacted),
                redactions=counts,
            )
        )
    return exported


def _bundle_digest(memory_dir: Path) -> str:
    """Hash the complete ordered set of conversation-memory files."""
    digest = hashlib.sha256()
    for path in sorted(memory_dir.glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _is_adapter_bundle(path: Path) -> bool:
    """Return whether a directory has this adapter's recognizable marker."""
    if not path.is_dir() or path.is_symlink():
        return False
    manifest_path = path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    adapter = manifest.get("adapter")
    return isinstance(adapter, str) and adapter == BUNDLE_ADAPTER


def export_bundle(args: argparse.Namespace) -> dict[str, Any]:
    """Export selected rollout messages into a validated OKF bundle."""
    source = args.source.resolve()
    output = args.output.resolve()
    parse_stats = ParseStats()
    records = list(iter_message_records(source, parse_stats))
    include = re.compile(args.include, re.IGNORECASE) if args.include else None
    exclude = re.compile(args.exclude, re.IGNORECASE) if args.exclude else None
    selected = select_records(
        records,
        roles=set(args.roles),
        include=include,
        exclude=exclude,
        max_records=args.max_records,
        take=args.take,
    )
    if not selected:
        raise ValueError("no conversation records matched the selection")
    exported = _build_exported(selected, args.redact_literal)

    if output.exists():
        if not args.force:
            raise FileExistsError(f"output already exists: {output} (use --force)")
        if not _is_adapter_bundle(output):
            raise ValueError(
                f"refusing --force for non-{BUNDLE_ADAPTER} output: {output}"
            )
        shutil.rmtree(output)
    memory_dir = output / "memories" / "conversation"
    memory_dir.mkdir(parents=True)
    for item in exported:
        (memory_dir / _slug(item)).write_text(_render_entry(item), encoding="utf-8")

    index_lines = [
        "---",
        "type: index",
        'title: "Codex CLI conversation memories"',
        "---",
        "",
        "# Codex CLI conversation memories",
        "",
    ]
    for path in sorted(memory_dir.glob("*.md")):
        index_lines.append(f"- [{path.stem}](conversation/{path.name})")
    (output / "memories" / "index.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )

    redaction_totals: Counter[str] = Counter()
    for item in exported:
        redaction_totals.update(item.redactions)
    source_size = source.stat().st_size
    selected_source_text_bytes = sum(
        len(item.record.text.encode("utf-8")) for item in exported
    )
    published_content_bytes = sum(
        len(item.redacted_text.encode("utf-8")) for item in exported
    )
    role_counts = Counter(item.record.role for item in exported)
    manifest = {
        "adapter": BUNDLE_ADAPTER,
        "adapter_version": ADAPTER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "sha256": _sha256_file(source),
            "bytes": source_size,
            "conversation_messages": len(records),
            "unparseable_lines_skipped": parse_stats.unparseable_lines,
            "path_published": False,
        },
        "selection": {
            "roles": sorted(set(args.roles)),
            "include_filter_applied": bool(args.include),
            "exclude_filter_applied": bool(args.exclude),
            "take": args.take,
            "max_records": args.max_records,
            "selected": len(exported),
        },
        "migration_summary": {
            "source_conversation_messages": len(records),
            "selected_source_records": len(exported),
            "mapped_okf_memories": len(exported),
            "skipped_selected_records": 0,
            "per_role": dict(sorted(role_counts.items())),
        },
        "privacy": {
            "raw_text_published": False,
            "literal_values_persisted": False,
            "redactions": dict(sorted(redaction_totals.items())),
            "gate_findings": 0,
        },
        "savings_report": {
            "source_rollout_bytes": source_size,
            "selected_source_text_bytes": selected_source_text_bytes,
            "published_redacted_text_bytes": published_content_bytes,
            "source_api_calls": 0,
            "migration_api_calls": 0,
            "token_savings": "not_applicable_local_source",
            "latency_savings": "not_applicable_local_source",
            "note": (
                "Codex rollouts and OKF are local files; no cost or latency "
                "baseline is invented."
            ),
        },
        "records": [
            {
                "entry_id": item.entry_id,
                "role": item.record.role,
                "source_line": item.record.line_number,
                "source_record_sha256": item.record.source_record_sha256,
                "content_sha256": item.content_sha256,
                "redaction_count": sum(item.redactions.values()),
            }
            for item in exported
        ],
    }
    manifest_path = output / "manifest.json"
    manifest["bundle_sha256"] = _bundle_digest(memory_dir)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


FRONTMATTER_FIELD_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<value>.*)$", re.MULTILINE
)


def _parse_entry_for_validation(path: Path) -> dict[str, Any]:
    """Parse the small frontmatter subset emitted by this adapter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"invalid OKF frontmatter: {path}")
    frontmatter, body = text[4:].split("\n---\n", 1)
    fields: dict[str, Any] = {}
    for match in FRONTMATTER_FIELD_RE.finditer(frontmatter):
        raw_value = match.group("value")
        try:
            fields[match.group("key")] = json.loads(raw_value)
        except json.JSONDecodeError:
            fields[match.group("key")] = raw_value
    body_lines = body.strip().splitlines()
    content = "\n".join(body_lines[2:]).strip() if len(body_lines) >= 2 else ""
    fields["_content"] = content
    fields["_path"] = str(path)
    return fields


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STOPWORDS = {
    "a",
    "al",
    "and",
    "como",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "how",
    "la",
    "las",
    "los",
    "of",
    "por",
    "que",
    "the",
    "to",
    "un",
    "una",
    "y",
}


def _tokens(text: str) -> set[str]:
    """Return normalized lexical tokens for deterministic recall checks."""
    return {
        token
        for token in TOKEN_RE.findall(text.casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def _retrieve(query: str, documents: dict[str, str]) -> str | None:
    """Retrieve one document with a deterministic lexical-overlap score."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return None
    ranked: list[tuple[float, str]] = []
    for record_hash, text in documents.items():
        document_tokens = _tokens(text)
        overlap = query_tokens & document_tokens
        if not overlap:
            continue
        # Reward coverage first and mildly penalize very broad documents. The
        # same deterministic scorer is used before and after migration.
        score = len(overlap) / len(query_tokens) + len(overlap) / max(
            len(document_tokens), 1
        )
        ranked.append((score, record_hash))
    return max(ranked, default=(0.0, None))[1]


def _normalize_evidence(text: str) -> str:
    """Normalize whitespace and case for answer-evidence comparisons."""
    return " ".join(text.casefold().split())


def validate_golden_recall(
    golden_path: Path,
    source_documents: dict[str, str],
    okf_documents: dict[str, str],
) -> dict[str, Any]:
    """Score deterministic golden-Q&A recall before and after migration."""
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    questions = payload.get("questions", [])
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"golden Q&A has no questions: {golden_path}")
    results: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("golden Q&A entries must be objects")
        question = str(item.get("question") or "")
        expected = str(item.get("expected_source_record_sha256") or "")
        evidence = item.get("answer_contains") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not question or not expected or not isinstance(evidence, list):
            raise ValueError("golden Q&A entry is missing required fields")
        source_match = _retrieve(question, source_documents)
        okf_match = _retrieve(question, okf_documents)
        source_text = _normalize_evidence(source_documents.get(expected, ""))
        okf_text = _normalize_evidence(okf_documents.get(expected, ""))
        evidence_values = [
            _normalize_evidence(str(value)) for value in evidence if str(value).strip()
        ]
        source_evidence = all(value in source_text for value in evidence_values)
        okf_evidence = all(value in okf_text for value in evidence_values)
        results.append(
            {
                "id": str(item.get("id") or len(results) + 1),
                "source_retrieved_expected": source_match == expected,
                "okf_retrieved_expected": okf_match == expected,
                "retrieval_parity": source_match == okf_match,
                "source_answer_evidence": source_evidence,
                "okf_answer_evidence": okf_evidence,
            }
        )
    correct = sum(
        row["source_retrieved_expected"]
        and row["okf_retrieved_expected"]
        and row["retrieval_parity"]
        and row["source_answer_evidence"]
        and row["okf_answer_evidence"]
        for row in results
    )
    return {
        "questions": len(results),
        "fully_correct": correct,
        "recall_parity_score": correct / len(results),
        "results": results,
    }


def validate_bundle(args: argparse.Namespace) -> dict[str, Any]:
    """Validate source linkage, entry integrity, privacy, and golden recall."""
    source = args.source.resolve()
    bundle = args.bundle.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source_digest = _sha256_file(source)
    parse_stats = ParseStats()
    source_records = list(iter_message_records(source, parse_stats))
    source_documents = {
        record.source_record_sha256: record.text for record in source_records
    }
    source_hashes = set(source_documents)
    okf_entries = [
        _parse_entry_for_validation(path)
        for path in sorted((bundle / "memories" / "conversation").glob("*.md"))
    ]

    failures: list[str] = []
    content_hash_mismatches = 0
    privacy_gate_issue_count = 0
    if source_digest != manifest["source"]["sha256"]:
        failures.append("source digest differs from manifest")
    if parse_stats.unparseable_lines != manifest["source"].get(
        "unparseable_lines_skipped", 0
    ):
        failures.append("unparseable source-line count differs from manifest")
    manifest_records = {
        row["source_record_sha256"]: row for row in manifest.get("records", [])
    }
    okf_source_hashes: set[str] = set()
    okf_documents: dict[str, str] = {}
    for entry in okf_entries:
        source_hash = str(entry.get("source_record_sha256", ""))
        okf_source_hashes.add(source_hash)
        okf_documents[source_hash] = str(entry.get("_content", ""))
        if source_hash not in source_hashes:
            failures.append(
                f"OKF entry has no matching source record: {source_hash[:16]}"
            )
        expected = str(entry.get("content_sha256", ""))
        actual = _sha256_text(str(entry.get("_content", "")))
        if actual != expected:
            content_hash_mismatches += 1
            failures.append(f"content hash mismatch: {entry['_path']}")
        manifest_expected = str(
            manifest_records.get(source_hash, {}).get("content_sha256", "")
        )
        if actual != manifest_expected:
            content_hash_mismatches += 1
            failures.append(f"manifest content hash mismatch: {entry['_path']}")
        # The adapter controls frontmatter metadata and hashes. Scan the only
        # user-derived published field so timestamps and digests cannot be
        # mistaken for phone numbers.
        findings = privacy_findings(str(entry.get("_content", "")))
        if findings:
            privacy_gate_issue_count += len(findings)
            failures.append(
                f"privacy gate failed for {entry['_path']}: {', '.join(findings)}"
            )
    if set(manifest_records) != okf_source_hashes:
        failures.append("manifest and OKF source-record sets differ")
    digest = _bundle_digest(bundle / "memories" / "conversation")
    if digest != manifest.get("bundle_sha256"):
        failures.append("bundle digest differs from manifest")

    golden_path = getattr(args, "golden", None)
    if golden_path is None:
        default_golden = bundle / "golden_questions.json"
        golden_path = default_golden if default_golden.exists() else None
    golden_report = None
    if golden_path is not None:
        golden_report = validate_golden_recall(
            Path(golden_path), source_documents, okf_documents
        )
        if golden_report["recall_parity_score"] != 1.0:
            failures.append("golden Q&A recall parity is below 100%")

    selected = len(manifest_records)
    matched = len(okf_source_hashes & source_hashes)
    report = {
        "valid": not failures,
        "adapter_version": ADAPTER_VERSION,
        "source_sha256_match": source_digest == manifest["source"]["sha256"],
        "selected_source_records": selected,
        "okf_entries": len(okf_entries),
        "source_to_okf_matched": matched,
        "source_to_okf_coverage": matched / selected if selected else 0.0,
        "content_hash_parity": content_hash_mismatches == 0,
        "privacy_gate_findings": privacy_gate_issue_count,
        "golden_qa": golden_report,
        "bundle_sha256": digest,
        "failures": failures,
    }
    if args.report:
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the export and validation command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="export a rollout JSONL to OKF")
    export.add_argument("source", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument(
        "--roles",
        nargs="+",
        choices=("user", "assistant"),
        default=["user", "assistant"],
    )
    export.add_argument(
        "--include", help="case-insensitive regex applied before redaction"
    )
    export.add_argument("--exclude", help="case-insensitive exclusion regex")
    export.add_argument("--max-records", type=int, default=100)
    export.add_argument("--take", choices=("first", "last"), default="last")
    export.add_argument(
        "--redact-literal",
        action="append",
        default=[],
        help="private literal to replace; repeatable and never stored",
    )
    export.add_argument("--force", action="store_true")

    validate = subparsers.add_parser(
        "validate", help="prove source provenance, content parity, and privacy"
    )
    validate.add_argument("source", type=Path)
    validate.add_argument("bundle", type=Path)
    validate.add_argument("--report", type=Path)
    validate.add_argument("--golden", type=Path, help="optional golden Q&A JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested CLI action and return a shell-friendly exit code."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "export":
            result = export_bundle(args)
            summary = {
                "selected": result["selection"]["selected"],
                "redactions": result["privacy"]["redactions"],
                "bundle_sha256": result["bundle_sha256"],
            }
        else:
            result = validate_bundle(args)
            summary = result
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if result.get("valid", True) else 1
    except (FileNotFoundError, FileExistsError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

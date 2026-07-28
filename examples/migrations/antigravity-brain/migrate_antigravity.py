#!/usr/bin/env python3
"""Convert Google Antigravity brain artifacts into a Memanto OKF bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import shutil
import zlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

BUNDLE_SENTINEL = ".antigravity-okf-bundle-v1"
SOURCE_MARKER_PREFIX = "<!-- antigravity-source-v1:"
SOURCE_MARKER_RE = re.compile(r"<!-- antigravity-source-v1:([A-Za-z0-9+/=]+) -->")
MAX_SOURCE_BYTES = 8 * 1024 * 1024
CHUNK_CHARS = 3_000

ARTIFACT_TYPES: dict[str, tuple[str, str]] = {
    "ARTIFACT_TYPE_TASK": ("commitment", "Task"),
    "ARTIFACT_TYPE_IMPLEMENTATION_PLAN": ("goal", "Implementation plan"),
    "ARTIFACT_TYPE_WALKTHROUGH": ("learning", "Walkthrough"),
}

_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL_RE = re.compile(r"https?://[^\s)>\]}*]+")
_WINDOWS_PATH_RE = re.compile(r"(?i)(?<!\w)/?[A-Z]:[\\/][^\s`\"')\]}*]+")
_UNIX_HOME_RE = re.compile(r"(?<!\w)/(?:home|Users)/[^\s`\"']+")
_IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_UUID_RE = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)(\b(?:api[_-]?key|access[_-]?token|secret|password|bearer)\b"
    r"\s*[:=]\s*)([^\s,;]+)"
)


@dataclass(frozen=True)
class Artifact:
    """One canonical Antigravity brain artifact and its sidecar metadata."""

    session_id: str
    relative_path: PurePosixPath
    content: bytes
    metadata_name: str | None
    metadata: bytes | None
    artifact_type: str
    updated_at: str | None


@dataclass(frozen=True)
class RenderedMemory:
    """One importable OKF memory, possibly a chunk of a larger artifact."""

    memory_type: str
    title: str
    filename: str
    text: str


def sha256_bytes(data: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def stable_session_alias(session_id: str) -> str:
    """Pseudonymize a local conversation identifier deterministically."""
    return f"session-{sha256_bytes(session_id.encode())[:12]}"


def _safe_session_id(value: str) -> str:
    if not _SESSION_RE.fullmatch(value):
        raise ValueError(f"Unsafe Antigravity session identifier: {value!r}")
    return value


def _safe_child(root: Path, child: Path) -> Path:
    root_resolved = root.resolve()
    resolved = child.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"Path escapes the source root: {child}")
    if child.is_symlink():
        raise ValueError(f"Symlinks are not accepted as migration input: {child}")
    return resolved


def _read_limited(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"Artifact exceeds the {MAX_SOURCE_BYTES}-byte limit: {path}")
    return path.read_bytes()


def _load_metadata(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = _read_limited(path)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid UTF-8 JSON metadata: {path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Metadata must be a JSON object: {path}")
    return raw, parsed


def discover_artifacts(
    antigravity_root: Path, conversation: str | None = None
) -> list[Artifact]:
    """Discover canonical ``*.md`` brain artifacts, excluding revision files."""
    root = antigravity_root.expanduser().resolve()
    brain_root = root / "brain"
    if not brain_root.is_dir():
        raise FileNotFoundError(f"Antigravity brain directory not found: {brain_root}")

    requested = _safe_session_id(conversation) if conversation else None
    session_dirs = sorted(path for path in brain_root.iterdir() if path.is_dir())
    if requested:
        session_dirs = [path for path in session_dirs if path.name == requested]
        if not session_dirs:
            raise FileNotFoundError(f"Antigravity session not found: {requested}")

    artifacts: list[Artifact] = []
    for session_dir in session_dirs:
        session_id = _safe_session_id(session_dir.name)
        _safe_child(brain_root, session_dir)
        candidates = [
            path
            for path in session_dir.glob("*.md*")
            if path.name.endswith(".md")
            or re.search(r"\.md\.resolved\.\d+$", path.name)
        ]
        for path in sorted(candidates):
            _safe_child(session_dir, path)
            content = _read_limited(path)
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Brain artifact is not UTF-8: {path}") from exc

            canonical_name = re.sub(r"\.resolved\.\d+$", "", path.name)
            metadata_path = path.with_name(canonical_name + ".metadata.json")
            metadata_raw: bytes | None = None
            metadata: dict[str, Any] = {}
            if metadata_path.is_file():
                _safe_child(session_dir, metadata_path)
                loaded_raw, metadata = _load_metadata(metadata_path)
                if path.name.endswith(".md"):
                    metadata_raw = loaded_raw

            artifact_type = str(metadata.get("artifactType") or "ARTIFACT_TYPE_UNKNOWN")
            updated_at = metadata.get("updatedAt")
            if updated_at is not None and not isinstance(updated_at, str):
                raise ValueError(f"updatedAt must be a string: {metadata_path}")
            artifacts.append(
                Artifact(
                    session_id=session_id,
                    relative_path=PurePosixPath("brain", session_id, path.name),
                    content=content,
                    metadata_name=metadata_path.name
                    if metadata_raw is not None
                    else None,
                    metadata=metadata_raw,
                    artifact_type=artifact_type,
                    updated_at=updated_at,
                )
            )

    if not artifacts:
        scope = f" for session {requested}" if requested else ""
        raise ValueError(f"No canonical Antigravity brain artifacts found{scope}")
    return artifacts


def redact_text(
    text: str, custom_redactions: dict[str, str] | None = None
) -> tuple[str, Counter[str]]:
    """Apply deterministic publication-safe redactions to text."""
    counts: Counter[str] = Counter()

    crlf_count = text.count("\r\n")
    lone_cr_count = text.count("\r") - crlf_count
    if crlf_count or lone_cr_count:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        counts["line_endings_normalized"] = crlf_count + lone_cr_count

    def replace(pattern: re.Pattern[str], replacement: str, label: str) -> None:
        nonlocal text
        text, count = pattern.subn(replacement, text)
        counts[label] += count

    def replace_secret(match: re.Match[str]) -> str:
        counts["secret_assignment"] += 1
        return match.group(1) + "[redacted-secret]"

    text = _SECRET_ASSIGNMENT_RE.sub(replace_secret, text)
    replace(_EMAIL_RE, "[redacted-email]", "email")
    replace(_URL_RE, "[redacted-url]", "url")
    replace(_WINDOWS_PATH_RE, "[redacted-path]", "windows_path")
    replace(_UNIX_HOME_RE, "[redacted-path]", "unix_home")
    replace(_IP_RE, "[redacted-ip]", "ip_address")
    replace(_UUID_RE, "[session-id]", "uuid")

    for needle, replacement in sorted((custom_redactions or {}).items()):
        if not needle:
            raise ValueError("Custom redaction keys must not be empty")
        count = text.count(needle)
        if count:
            text = text.replace(needle, replacement)
            counts["custom"] += count
    return text, counts


def sanitize_artifact(
    artifact: Artifact, custom_redactions: dict[str, str] | None = None
) -> tuple[Artifact, Counter[str]]:
    """Return a publishable artifact while retaining exact sanitized bytes."""
    content, counts = redact_text(artifact.content.decode("utf-8"), custom_redactions)
    metadata_raw = artifact.metadata
    if metadata_raw is not None:
        metadata_text, metadata_counts = redact_text(
            metadata_raw.decode("utf-8"), custom_redactions
        )
        counts.update(metadata_counts)
        metadata_raw = metadata_text.encode("utf-8")

    alias = stable_session_alias(artifact.session_id)
    return (
        Artifact(
            session_id=alias,
            relative_path=PurePosixPath("brain", alias, artifact.relative_path.name),
            content=content.encode("utf-8"),
            metadata_name=artifact.metadata_name,
            metadata=metadata_raw,
            artifact_type=artifact.artifact_type,
            updated_at=artifact.updated_at,
        ),
        counts,
    )


def _artifact_mapping(artifact_type: str, filename: str) -> tuple[str, str]:
    revision = re.search(r"\.resolved\.(\d+)$", filename)
    if artifact_type in ARTIFACT_TYPES:
        memory_type, title = ARTIFACT_TYPES[artifact_type]
        if revision:
            return "event", f"{title} revision {revision.group(1)}"
        return memory_type, title
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    title = stem[:1].upper() + stem[1:] if stem else "Antigravity artifact"
    return "artifact", title


def _split_text(text: str) -> list[str]:
    return [
        text[index : index + CHUNK_CHARS] for index in range(0, len(text), CHUNK_CHARS)
    ] or [""]


def _encode_source_record(record: dict[str, Any]) -> str:
    raw = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    compressed = zlib.compress(raw.encode("utf-8"), level=9)
    return base64.b64encode(compressed).decode("ascii")


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result[:60].rstrip("-") or "artifact"


def render_artifact(artifact: Artifact) -> list[RenderedMemory]:
    """Render one source artifact as one or more size-safe OKF memories."""
    memory_type, base_title = _artifact_mapping(
        artifact.artifact_type, artifact.relative_path.name
    )
    text = artifact.content.decode("utf-8")
    chunks = _split_text(text)
    artifact_id = sha256_bytes(
        f"{artifact.session_id}/{artifact.relative_path.name}".encode()
    )[:20]
    rendered: list[RenderedMemory] = []

    for index, chunk in enumerate(chunks):
        part = index + 1
        title = (
            base_title
            if len(chunks) == 1
            else f"{base_title} (part {part}/{len(chunks)})"
        )
        record = {
            "artifact_id": artifact_id,
            "artifact_type": artifact.artifact_type,
            "content_b64": base64.b64encode(chunk.encode("utf-8")).decode("ascii"),
            "content_sha256": sha256_bytes(chunk.encode("utf-8")),
            "metadata_b64": (
                base64.b64encode(artifact.metadata).decode("ascii")
                if index == 0 and artifact.metadata is not None
                else None
            ),
            "metadata_name": artifact.metadata_name,
            "part_count": len(chunks),
            "part_index": index,
            "relative_path": artifact.relative_path.as_posix(),
            "session_id": artifact.session_id,
            "version": 1,
        }
        marker = f"{SOURCE_MARKER_PREFIX}{_encode_source_record(record)} -->"
        body = chunk.rstrip("\r\n") + "\n\n" + marker
        timestamp = artifact.updated_at or "1970-01-01T00:00:00Z"
        resource = (
            f"antigravity://{artifact.session_id}/brain/"
            f"{artifact.relative_path.name}#part-{part}"
        )
        frontmatter = "\n".join(
            [
                "---",
                f"type: {memory_type}",
                f"title: {_yaml_string(title)}",
                f"description: {_yaml_string('Imported Antigravity ' + base_title.lower())}",
                f"resource: {_yaml_string(resource)}",
                f"tags: [{_yaml_string('antigravity')}, {_yaml_string(artifact.artifact_type.lower())}]",
                f"timestamp: {_yaml_string(timestamp)}",
                "x_memanto:",
                "  confidence: 1.0",
                "  provenance: imported",
                "  source: antigravity",
                "  status: active",
                f"  type: {memory_type}",
                "---",
                "",
            ]
        )
        full_text = frontmatter + body + "\n"
        if len(body) > 9_000:
            raise ValueError(
                f"Rendered memory exceeds the Memanto content budget: {artifact.relative_path}"
            )
        suffix = "" if len(chunks) == 1 else f"-part-{part:02d}"
        rendered.append(
            RenderedMemory(
                memory_type=memory_type,
                title=title,
                filename=f"{_slug(base_title)}{suffix}.md",
                text=full_text,
            )
        )
    return rendered


def file_entropy(path: Path) -> float:
    """Calculate Shannon entropy without retaining source contents."""
    data = path.read_bytes()
    if not data:
        return 0.0
    counts = Counter(data)
    return -sum(
        (count / len(data)) * math.log2(count / len(data)) for count in counts.values()
    )


def source_provenance(
    antigravity_root: Path, sessions: Iterable[str]
) -> list[dict[str, Any]]:
    """Record privacy-safe metadata for Antigravity's opaque conversation files."""
    result: list[dict[str, Any]] = []
    for session_id in sorted(set(sessions)):
        path = antigravity_root / "conversations" / f"{session_id}.pb"
        if not path.is_file():
            continue
        _safe_child(antigravity_root, path)
        entropy = file_entropy(path)
        result.append(
            {
                "session_id": session_id,
                "filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
                "shannon_entropy_bits_per_byte": round(entropy, 5),
                "opaque_or_encrypted": entropy >= 7.9,
                "contents_published": False,
            }
        )
    return result


def attachment_manifest(
    antigravity_root: Path, sessions: Iterable[str]
) -> list[dict[str, Any]]:
    """Inventory non-text brain artifacts by size and digest only."""
    rows: list[dict[str, Any]] = []
    for session_id in sorted(set(sessions)):
        session_dir = antigravity_root / "brain" / session_id
        if not session_dir.is_dir():
            continue
        for path in sorted(session_dir.iterdir()):
            if not path.is_file() or path.name.endswith(".metadata.json"):
                continue
            if path.suffix.lower() in {".md", ".resolved"} or ".resolved." in path.name:
                continue
            _safe_child(session_dir, path)
            rows.append(
                {
                    "session_id": session_id,
                    "filename": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_bytes(path.read_bytes()),
                    "included_in_okf": False,
                }
            )
    return rows


def _prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        sentinel = output / BUNDLE_SENTINEL
        if not force:
            raise FileExistsError(f"Output already exists (use --force): {output}")
        if not sentinel.is_file():
            raise ValueError(
                f"Refusing to replace a directory not created by this tool: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / BUNDLE_SENTINEL).write_text("1\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _prepared_sample_provenance(
    source_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]] | None:
    path = source_root / "source-provenance.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Prepared sample provenance must be a JSON object")
    conversations = value.get("opaque_conversation_provenance", [])
    attachments = value.get("attachment_provenance", [])
    if not isinstance(conversations, list) or not isinstance(attachments, list):
        raise ValueError("Prepared sample provenance lists are malformed")
    return conversations, attachments, value


def _write_index(path: Path, title: str, links: list[tuple[str, str]]) -> None:
    lines = [
        "---",
        "type: index",
        f"title: {_yaml_string(title)}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    lines.extend(f"- [{label}]({target})" for label, target in links)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def migrate(
    antigravity_root: Path,
    output: Path,
    *,
    conversation: str | None = None,
    publishable: bool = False,
    custom_redactions: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create an importable OKF bundle and return its migration report."""
    source_root = antigravity_root.expanduser().resolve()
    artifacts = discover_artifacts(source_root, conversation)
    redaction_counts: Counter[str] = Counter()
    if publishable:
        sanitized: list[Artifact] = []
        for artifact in artifacts:
            clean, counts = sanitize_artifact(artifact, custom_redactions)
            sanitized.append(clean)
            redaction_counts.update(counts)
        artifacts = sanitized

    _prepare_output(output, force)
    memories_root = output / "memories"
    links_by_type: dict[str, list[tuple[str, str]]] = {}
    counts_by_type: Counter[str] = Counter()
    written: list[RenderedMemory] = []
    used_names: dict[str, set[str]] = {}

    for artifact in artifacts:
        for memory in render_artifact(artifact):
            type_dir = memories_root / memory.memory_type
            type_dir.mkdir(parents=True, exist_ok=True)
            used = used_names.setdefault(memory.memory_type, set())
            filename = memory.filename
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            counter = 2
            while filename in used:
                filename = f"{stem}-{counter}{suffix}"
                counter += 1
            used.add(filename)
            (type_dir / filename).write_bytes(memory.text.encode("utf-8"))
            links_by_type.setdefault(memory.memory_type, []).append(
                (memory.title, filename)
            )
            counts_by_type[memory.memory_type] += 1
            written.append(memory)

    for memory_type, links in sorted(links_by_type.items()):
        _write_index(memories_root / memory_type / "index.md", memory_type, links)
    _write_index(
        memories_root / "index.md",
        "Antigravity memories",
        [
            (memory_type, f"{memory_type}/index.md")
            for memory_type in sorted(links_by_type)
        ],
    )
    _write_index(
        output / "index.md",
        "Antigravity brain migration",
        [("Memories", "memories/index.md")],
    )

    sessions = [artifact.session_id for artifact in artifacts]
    prepared_provenance = _prepared_sample_provenance(source_root)
    prepared_manifest: dict[str, Any] = {}
    provenance_sessions = sessions
    if prepared_provenance is not None:
        provenance, attachments, prepared_manifest = prepared_provenance
    elif publishable:
        original_sessions = sorted(
            {item.session_id for item in discover_artifacts(source_root, conversation)}
        )
        provenance = source_provenance(source_root, original_sessions)
        for row in provenance:
            row["session_id"] = stable_session_alias(str(row["session_id"]))
            row["filename"] = f"{row['session_id']}.pb"
        attachments = attachment_manifest(source_root, original_sessions)
        for row in attachments:
            row["session_id"] = stable_session_alias(str(row["session_id"]))
    else:
        provenance = source_provenance(source_root, provenance_sessions)
        attachments = attachment_manifest(source_root, provenance_sessions)

    source_bytes = sum(
        len(artifact.content) + len(artifact.metadata or b"") for artifact in artifacts
    )
    okf_bytes = sum(len(memory.text.encode("utf-8")) for memory in written)
    report = {
        "adapter": "antigravity-brain-v1",
        "source_artifacts": len(artifacts),
        "mapped_memories": len(written),
        "skipped": 0,
        "type_breakdown": dict(sorted(counts_by_type.items())),
        "sessions": len(set(sessions)),
        "source_text_and_metadata_bytes": source_bytes,
        "importable_okf_bytes": okf_bytes,
        "publishable_mode": publishable or prepared_provenance is not None,
        "lossless_payloads": len(written),
    }
    metrics = output / "metrics"
    _write_json(metrics / "migration-report.json", report)
    _write_json(
        metrics / "source-provenance.json",
        {"conversation_files": provenance, "attachments": attachments},
    )
    _write_json(
        metrics / "privacy-report.json",
        {
            "publishable_mode": publishable or prepared_provenance is not None,
            "prepared_publishable_input": prepared_provenance is not None,
            "redactions": (
                dict(sorted(redaction_counts.items()))
                if prepared_provenance is None
                else prepared_manifest.get("redactions", {})
            ),
            "raw_conversation_contents_published": False,
        },
    )
    _write_json(
        metrics / "savings-report.json",
        {
            "provider_cost_savings": None,
            "provider_latency_savings": None,
            "provider_token_savings": None,
            "reason": "Antigravity brain artifacts are local files with no provider billing baseline.",
            "source_bytes": source_bytes,
            "okf_bytes": okf_bytes,
            "storage_delta_bytes": okf_bytes - source_bytes,
        },
    )
    (metrics / "mapping-table.md").write_text(
        "# Antigravity → Memanto mapping\n\n"
        "| Antigravity concept | Memanto type | OKF representation |\n"
        "| --- | --- | --- |\n"
        "| Task artifact | `commitment` | Readable Markdown body |\n"
        "| Implementation plan | `goal` | Readable Markdown body |\n"
        "| Walkthrough | `learning` | Readable Markdown body |\n"
        "| Unknown brain artifact | `artifact` | Readable Markdown body |\n"
        "| Artifact metadata | Namespaced source marker | Compressed exact sidecar |\n"
        "| Images and opaque `.pb` | Provenance manifest | SHA-256, size, no private bytes |\n",
        encoding="utf-8",
    )
    return report


def _load_redactions(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("Redactions file must be a JSON object of string replacements")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to ~/.gemini/antigravity")
    parser.add_argument("output", type=Path, help="Destination OKF bundle")
    parser.add_argument("--conversation", help="Migrate only this conversation ID")
    parser.add_argument(
        "--publishable",
        action="store_true",
        help="Pseudonymize session IDs and redact common private values",
    )
    parser.add_argument(
        "--redactions",
        type=Path,
        help="Optional JSON object of additional exact replacements",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = migrate(
        args.source,
        args.output,
        conversation=args.conversation,
        publishable=args.publishable,
        custom_redactions=_load_redactions(args.redactions),
        force=args.force,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

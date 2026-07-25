#!/usr/bin/env python3
"""Export a Hindsight memory bank as a portable OKF 0.2 bundle.

The adapter intentionally uses only Python's standard library. It can read a
live Hindsight API or replay a captured source snapshot. Valid memories are
written below ``memories/`` for ``memanto migrate okf``. Invalidated Hindsight
records remain losslessly available below ``archive/`` but are not re-imported
as active memories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADAPTER_VERSION = "1.0.0"
SNAPSHOT_SCHEMA = "hindsight-memory-snapshot/v1"
MANIFEST_SCHEMA = "hindsight-okf-manifest/v1"
PAGE_SIZE = 100
MEMANTO_TYPES = {
    "world": "fact",
    "experience": "event",
    "observation": "learning",
}
BASE_CONFIDENCE = {
    "world": 0.90,
    "experience": 0.85,
    "observation": 0.80,
}
RESERVED_FILENAMES = {"index.md", "log.md"}
ENTRY_DELIMITER = "<!-- okf-entry -->"


class AdapterError(RuntimeError):
    """Raised for a user-actionable migration failure."""


def utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any, *, pretty: bool = False) -> str:
    """Serialize a value deterministically while retaining Unicode text."""
    if pretty:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_json(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible value."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def api_memory_url(base_url: str, bank_id: str, memory_id: str | None = None) -> str:
    """Build the canonical Hindsight URL for a bank or individual memory."""
    quoted_bank = urllib.parse.quote(bank_id, safe="")
    root = f"{base_url.rstrip('/')}/v1/default/banks/{quoted_bank}/memories"
    if memory_id is None:
        return f"{root}/list"
    return f"{root}/{urllib.parse.quote(memory_id, safe='')}"


def request_json(url: str, *, api_token: str | None, timeout: float) -> Any:
    """Issue an authenticated GET request and decode its JSON response."""
    headers = {
        "Accept": "application/json",
        "User-Agent": f"memanto-hindsight-okf/{ADAPTER_VERSION}",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise AdapterError(
            f"Hindsight returned HTTP {exc.code} for {url}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AdapterError(f"Could not reach Hindsight at {url}: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AdapterError(f"Hindsight returned invalid JSON for {url}") from exc


def fetch_memory_state(
    *,
    base_url: str,
    bank_id: str,
    state: str,
    api_token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    """Fetch one Hindsight curation state, following offset pagination."""
    if state not in {"valid", "invalidated"}:
        raise AdapterError(f"Unsupported Hindsight state: {state}")

    endpoint = api_memory_url(base_url, bank_id)
    offset = 0
    total: int | None = None
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    while total is None or offset < total:
        query = urllib.parse.urlencode(
            {"state": state, "limit": PAGE_SIZE, "offset": offset}
        )
        payload = request_json(
            f"{endpoint}?{query}",
            api_token=api_token,
            timeout=timeout,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise AdapterError(
                "Unexpected Hindsight list response: expected an object with items[]"
            )
        try:
            page_total = int(payload["total"])
            response_offset = int(payload["offset"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterError(
                "Unexpected Hindsight list response: total/offset must be integers"
            ) from exc
        if response_offset != offset:
            raise AdapterError(
                f"Hindsight pagination drift: requested offset {offset}, "
                f"received {response_offset}"
            )
        total = page_total
        page = payload["items"]
        if not page and offset < total:
            raise AdapterError(
                f"Hindsight returned an empty page at offset {offset} of {total}"
            )

        for raw_record in page:
            record = validate_record(raw_record, state=state)
            record_id = record["id"]
            if record_id in seen_ids:
                raise AdapterError(
                    f"Hindsight returned duplicate {state} memory id {record_id}"
                )
            seen_ids.add(record_id)
            records.append(record)
        offset += len(page)

    return records


def capture_snapshot(
    *,
    base_url: str,
    bank_id: str,
    api_token: str | None,
    timeout: float,
    include_invalidated: bool = True,
) -> dict[str, Any]:
    """Capture a real Hindsight bank into the adapter's replayable schema."""
    normalized_url = base_url.rstrip("/")
    records = fetch_memory_state(
        base_url=normalized_url,
        bank_id=bank_id,
        state="valid",
        api_token=api_token,
        timeout=timeout,
    )
    if include_invalidated:
        records.extend(
            fetch_memory_state(
                base_url=normalized_url,
                bank_id=bank_id,
                state="invalidated",
                api_token=api_token,
                timeout=timeout,
            )
        )
    records.sort(key=record_sort_key)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "source": {
            "provider": "hindsight",
            "bank_id": bank_id,
            "base_url": normalized_url,
            "captured_at": utc_now(),
            "included_states": sorted(
                ["valid", "invalidated"] if include_invalidated else ["valid"]
            ),
        },
        "items": records,
    }


def validate_record(raw_record: Any, *, state: str | None = None) -> dict[str, Any]:
    """Validate and normalize one Hindsight memory without dropping fields."""
    if not isinstance(raw_record, dict):
        raise AdapterError("Every Hindsight memory must be a JSON object")
    record = dict(raw_record)
    record_id = str(record.get("id") or "").strip()
    text = str(record.get("text") or "").strip()
    if not record_id:
        raise AdapterError("A Hindsight memory is missing its id")
    if not text:
        raise AdapterError(f"Hindsight memory {record_id} has no text")

    raw_state = str(state or record.get("state") or "valid").strip().lower()
    if raw_state not in {"valid", "invalidated"}:
        raise AdapterError(
            f"Hindsight memory {record_id} has unsupported state {raw_state!r}"
        )
    fact_type = str(record.get("fact_type") or "").strip().lower() or "unknown"

    record["id"] = record_id
    record["text"] = text
    record["state"] = raw_state
    record["fact_type"] = fact_type
    record["tags"] = normalize_string_list(record.get("tags"))
    record["entities"] = normalize_entities(record.get("entities"))
    metadata = record.get("metadata")
    record["metadata"] = metadata if isinstance(metadata, dict) else {}
    return record


def normalize_string_list(value: Any) -> list[str]:
    """Normalize a scalar or iterable to a deduplicated list of strings."""
    if value in (None, ""):
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return list(
        dict.fromkeys(str(item).strip() for item in values if str(item).strip())
    )


def normalize_entities(value: Any) -> list[str]:
    """Normalize Hindsight's comma-separated or array-shaped entity field."""
    if isinstance(value, str):
        values = value.split(",")
    else:
        values = value
    return normalize_string_list(values)


def record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return a stable ordering key for snapshot and bundle generation."""
    return (
        str(record.get("state") or "valid"),
        str(record.get("fact_type") or "unknown"),
        str(record.get("id") or ""),
    )


def load_snapshot(
    path: Path,
    *,
    bank_id_override: str | None = None,
    base_url_override: str | None = None,
) -> dict[str, Any]:
    """Load a captured adapter snapshot or a raw Hindsight list response."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdapterError(f"Source snapshot does not exist: {path}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AdapterError(f"Source snapshot is not valid UTF-8 JSON: {path}") from exc

    if isinstance(payload, list):
        items = payload
        source: dict[str, Any] = {}
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
        source = (
            payload.get("source") if isinstance(payload.get("source"), dict) else {}
        )
    else:
        raise AdapterError(
            "Source snapshot must be items[] or an object containing items[]"
        )

    bank_id = str(bank_id_override or source.get("bank_id") or "").strip()
    if not bank_id:
        raise AdapterError(
            "--bank-id is required when the source snapshot has no source.bank_id"
        )
    base_url = str(
        base_url_override or source.get("base_url") or "http://localhost:8888"
    ).rstrip("/")
    captured_at = str(source.get("captured_at") or "").strip() or utc_now()

    records = [validate_record(item) for item in items]
    identities: set[tuple[str, str]] = set()
    for record in records:
        identity = (record["state"], record["id"])
        if identity in identities:
            raise AdapterError(
                f"Source snapshot contains duplicate {identity[0]} memory "
                f"id {identity[1]}"
            )
        identities.add(identity)
    records.sort(key=record_sort_key)

    return {
        "schema": SNAPSHOT_SCHEMA,
        "source": {
            "provider": "hindsight",
            "bank_id": bank_id,
            "base_url": base_url,
            "captured_at": captured_at,
            "included_states": sorted({record["state"] for record in records}),
        },
        "items": records,
    }


def memory_type(record: dict[str, Any]) -> str:
    """Map a Hindsight memory class to the closest Memanto primitive."""
    return MEMANTO_TYPES.get(str(record.get("fact_type")), "observation")


def memory_confidence(record: dict[str, Any]) -> float:
    """Derive a conservative Memanto confidence from source evidence."""
    fact_type = str(record.get("fact_type"))
    base = BASE_CONFIDENCE.get(fact_type, 0.75)
    if fact_type == "observation":
        try:
            proof_count = max(1, int(record.get("proof_count") or 1))
        except (TypeError, ValueError):
            proof_count = 1
        base = min(0.95, base + min(proof_count - 1, 5) * 0.03)
    return round(base, 2)


def source_timestamp(record: dict[str, Any], *, fallback: str) -> str:
    """Choose the strongest available Hindsight source timestamp."""
    for key in (
        "edited_at",
        "invalidated_at",
        "consolidated_at",
        "mentioned_at",
        "occurred_start",
        "date",
    ):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return fallback


def title_from_text(text: str, *, limit: int = 88) -> str:
    """Create a compact title from memory text without changing its body."""
    title = re.sub(r"\s+", " ", text).strip()
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def description_from_text(text: str, *, limit: int = 180) -> str:
    """Create a one-line OKF description from memory text."""
    description = re.sub(r"\s+", " ", text).strip()
    if len(description) <= limit:
        return description
    return description[: limit - 1].rstrip() + "…"


def slugify(value: str, *, limit: int = 60) -> str:
    """Turn a display title into a portable ASCII path component."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (slug or "memory")[:limit].rstrip("-")


def yaml_value(value: Any) -> str:
    """Render a JSON flow value, which is also valid YAML 1.2."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(", ", ": "),
        sort_keys=True,
    )


def render_frontmatter(values: dict[str, Any]) -> str:
    """Render deterministic human-readable YAML frontmatter."""
    lines = ["---"]
    for key, value in values.items():
        if value not in (None, "", [], {}):
            lines.append(f"{key}: {yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def safe_body_text(value: Any) -> str:
    """Prevent source text from colliding with Memanto's stacked-entry marker."""
    return (
        str(value or "")
        .strip()
        .replace(
            ENTRY_DELIMITER,
            "&lt;!-- okf-entry --&gt;",
        )
    )


def render_memory(
    record: dict[str, Any],
    *,
    bank_id: str,
    base_url: str,
    captured_at: str,
) -> str:
    """Render one Hindsight record as a conformant OKF 0.2 concept."""
    record_id = record["id"]
    fact_type = str(record["fact_type"])
    mapped_type = memory_type(record)
    timestamp = source_timestamp(record, fallback=captured_at)
    resource = api_memory_url(base_url, bank_id, record_id)
    tags = list(
        dict.fromkeys(
            [
                *record.get("tags", []),
                "source:hindsight",
                f"hindsight:{fact_type}",
            ]
        )
    )
    source_details = {
        key: value
        for key, value in record.items()
        if key not in {"text", "state"} and value not in (None, "", [], {})
    }
    frontmatter = {
        "type": mapped_type,
        "title": title_from_text(record["text"]),
        "description": description_from_text(record["text"]),
        "resource": resource,
        "tags": tags,
        "sources": [
            {
                "id": f"hindsight-{record_id}",
                "resource": resource,
                "title": f"Hindsight {fact_type} memory {record_id}",
                "author": "process:hindsight",
                "last_modified": timestamp[:10],
            }
        ],
        "generated": {
            "by": f"memanto-hindsight-okf/{ADAPTER_VERSION}",
            "at": captured_at,
        },
        "status": "deprecated" if record["state"] == "invalidated" else "stable",
        # Memanto currently reads the v0.1 timestamp field for created_at.
        # Keep it alongside generated.at until its loader moves to OKF 0.2.
        "timestamp": timestamp,
        "x_memanto": {
            "type": mapped_type,
            "confidence": memory_confidence(record),
            "source": "hindsight",
            "status": ("invalidated" if record["state"] == "invalidated" else "active"),
            "source_id": record_id,
        },
        "x_hindsight": {
            "bank_id": bank_id,
            "state": record["state"],
            **source_details,
        },
    }

    body = safe_body_text(record["text"])
    context = safe_body_text(record.get("context"))
    entities = record.get("entities", [])
    provenance_lines = [
        f"- Hindsight memory ID: `{record_id}`",
        f"- Hindsight class: `{fact_type}`",
        f"- Curation state: `{record['state']}`",
    ]
    if record.get("document_id"):
        provenance_lines.append(f"- Source document: `{record['document_id']}`")
    if entities:
        provenance_lines.append(f"- Linked entities: {', '.join(entities)}")

    sections = [body]
    if context:
        sections.append(f"## Source context\n\n{context}")
    sections.append("## Provenance\n\n" + "\n".join(provenance_lines))
    return f"{render_frontmatter(frontmatter)}\n\n" + "\n\n".join(sections) + "\n"


def memory_filename(record: dict[str, Any]) -> str:
    """Create a deterministic collision-resistant filename for a memory."""
    digest = hashlib.sha256(record["id"].encode("utf-8")).hexdigest()[:10]
    return f"{slugify(title_from_text(record['text']))}--{digest}.md"


def write_text(path: Path, content: str) -> None:
    """Create parent directories and write one UTF-8 text artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_directory_index(
    title: str,
    entries: list[tuple[str, str, str]],
) -> str:
    """Render an OKF reserved index file with progressive-disclosure links."""
    lines = [f"# {title}", ""]
    for label, relative_path, description in entries:
        lines.append(f"- [{label}]({relative_path}) — {description}")
    return "\n".join(lines).rstrip() + "\n"


def write_concept_tree(
    root: Path,
    *,
    records: list[dict[str, Any]],
    bank_id: str,
    base_url: str,
    captured_at: str,
    title: str,
) -> dict[str, int]:
    """Write records grouped by Memanto type and return per-type counts."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[memory_type(record)].append(record)

    root_entries: list[tuple[str, str, str]] = []
    counts: dict[str, int] = {}
    for mapped_type in sorted(grouped):
        type_records = sorted(grouped[mapped_type], key=record_sort_key)
        counts[mapped_type] = len(type_records)
        type_dir = root / mapped_type
        concept_entries: list[tuple[str, str, str]] = []
        for record in type_records:
            filename = memory_filename(record)
            write_text(
                type_dir / filename,
                render_memory(
                    record,
                    bank_id=bank_id,
                    base_url=base_url,
                    captured_at=captured_at,
                ),
            )
            concept_entries.append(
                (
                    title_from_text(record["text"]),
                    filename,
                    description_from_text(record["text"]),
                )
            )
        write_text(
            type_dir / "index.md",
            render_directory_index(
                f"{mapped_type.title()} ({len(type_records)})",
                concept_entries,
            ),
        )
        root_entries.append(
            (
                mapped_type.title(),
                f"{mapped_type}/index.md",
                f"{len(type_records)} {mapped_type} memories",
            )
        )

    write_text(root / "index.md", render_directory_index(title, root_entries))
    return counts


def validate_output_path(output_dir: Path) -> Path:
    """Reject broad paths that would be unsafe to replace with ``--force``."""
    resolved = output_dir.expanduser().resolve()
    protected = {
        Path(resolved.anchor).resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
    }
    if resolved in protected:
        raise AdapterError(f"Refusing to use protected output path: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise AdapterError(f"Output path exists and is not a directory: {resolved}")
    return resolved


def build_bundle(
    snapshot: dict[str, Any],
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Atomically create an OKF bundle and return its migration manifest."""
    output = validate_output_path(output_dir)
    if output.exists() and any(output.iterdir()) and not force:
        raise AdapterError(
            f"Output directory is not empty: {output} (pass --force to replace it)"
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    source = snapshot["source"]
    bank_id = str(source["bank_id"])
    base_url = str(source["base_url"])
    captured_at = str(source["captured_at"])
    records = [validate_record(item) for item in snapshot["items"]]
    valid = [record for record in records if record["state"] == "valid"]
    invalidated = [record for record in records if record["state"] == "invalidated"]

    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=str(output.parent)))
    backup: Path | None = None
    try:
        valid_counts = write_concept_tree(
            temp / "memories",
            records=valid,
            bank_id=bank_id,
            base_url=base_url,
            captured_at=captured_at,
            title=f"Importable Hindsight memories ({len(valid)})",
        )
        archived_counts: dict[str, int] = {}
        if invalidated:
            archived_counts = write_concept_tree(
                temp / "archive" / "invalidated",
                records=invalidated,
                bank_id=bank_id,
                base_url=base_url,
                captured_at=captured_at,
                title=f"Invalidated Hindsight memories ({len(invalidated)})",
            )
            write_text(
                temp / "archive" / "index.md",
                render_directory_index(
                    "Hindsight archive",
                    [
                        (
                            "Invalidated memories",
                            "invalidated/index.md",
                            (
                                f"{len(invalidated)} records preserved for audit; "
                                "not imported into Memanto"
                            ),
                        )
                    ],
                ),
            )

        normalized_source = {
            "provider": "hindsight",
            "bank_id": bank_id,
            "base_url": base_url,
            "captured_at": captured_at,
            "included_states": sorted({record["state"] for record in records}),
        }
        normalized_snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "source": normalized_source,
            "items": sorted(records, key=record_sort_key),
        }
        snapshot_path = temp / "source" / "hindsight-memory-snapshot.json"
        write_text(
            snapshot_path, canonical_json(normalized_snapshot, pretty=True) + "\n"
        )

        manifest = {
            "schema": MANIFEST_SCHEMA,
            "adapter_version": ADAPTER_VERSION,
            "source": {
                "provider": "hindsight",
                "bank_id": bank_id,
                "base_url": base_url,
                "captured_at": captured_at,
                "snapshot_sha256": sha256_json(normalized_snapshot),
            },
            "migration": {
                "source_records": len(records),
                "importable_records": len(valid),
                "archived_records": len(invalidated),
                "type_counts": valid_counts,
                "archived_type_counts": archived_counts,
                "source_fact_type_counts": dict(
                    sorted(Counter(record["fact_type"] for record in records).items())
                ),
                "mapping": {
                    **MEMANTO_TYPES,
                    "unknown": "observation",
                },
            },
            "commands": {
                "dry_run": "memanto migrate okf <bundle-dir> --dry-run",
                "import": "memanto migrate okf <bundle-dir> --agent <agent-id>",
                "export": "memanto memory export --okf --agent <agent-id>",
            },
        }
        write_text(
            temp / "migration-manifest.json",
            canonical_json(manifest, pretty=True) + "\n",
        )

        root_entries = [
            (
                "Importable memories",
                "memories/index.md",
                f"{len(valid)} active records ready for `memanto migrate okf`",
            ),
            (
                "Source snapshot",
                "source/hindsight-memory-snapshot.json",
                "The exact replayable Hindsight API data used for this bundle",
            ),
            (
                "Migration manifest",
                "migration-manifest.json",
                "Counts, mapping, checksum, and next commands",
            ),
        ]
        if invalidated:
            root_entries.append(
                (
                    "Audit archive",
                    "archive/index.md",
                    (
                        f"{len(invalidated)} invalidated records retained without "
                        "reactivating them"
                    ),
                )
            )
        root_index = (
            "---\n"
            'okf_version: "0.2"\n'
            "---\n\n"
            f"# Hindsight → Memanto freedom bundle\n\n"
            f"Bank `{bank_id}` captured at `{captured_at}`.\n\n"
            + render_directory_index("Contents", root_entries)
        )
        write_text(temp / "index.md", root_index)
        assert_bundle_conformance(temp, expected_importable=len(valid))

        if output.exists():
            backup = output.with_name(f".{output.name}.backup-{os.getpid()}")
            if backup.exists():
                raise AdapterError(f"Temporary backup path already exists: {backup}")
            output.rename(backup)
        try:
            temp.rename(output)
        except Exception:
            if backup is not None and backup.exists() and not output.exists():
                backup.rename(output)
            raise
        if backup is not None:
            shutil.rmtree(backup)
        return manifest
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def assert_bundle_conformance(bundle: Path, *, expected_importable: int) -> None:
    """Run structural OKF checks before publishing a generated bundle."""
    concept_files = [
        path
        for path in bundle.rglob("*.md")
        if path.name.lower() not in RESERVED_FILENAMES
    ]
    for path in concept_files:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n") or "\n---\n" not in content[4:]:
            raise AdapterError(f"Generated concept has invalid frontmatter: {path}")
        frontmatter = content.split("\n---\n", 1)[0]
        if not re.search(r'(?m)^type:\s*".+"\s*$', frontmatter):
            raise AdapterError(f"Generated concept has no non-empty type: {path}")

    importable = [
        path
        for path in (bundle / "memories").rglob("*.md")
        if path.name.lower() not in RESERVED_FILENAMES
    ]
    if len(importable) != expected_importable:
        raise AdapterError(
            f"Bundle validation counted {len(importable)} importable concepts; "
            f"expected {expected_importable}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the adapter command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Export a live or captured Hindsight memory bank to a Memanto-ready "
            "OKF 0.2 bundle."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination OKF bundle directory.",
    )
    parser.add_argument(
        "--source-json",
        type=Path,
        help="Replay an adapter snapshot or raw Hindsight items[] JSON.",
    )
    parser.add_argument(
        "--base-url",
        help=(
            "Hindsight API URL. Defaults to the snapshot value or "
            "http://localhost:8888."
        ),
    )
    parser.add_argument(
        "--bank-id",
        help="Hindsight bank ID. Required for a live API export.",
    )
    parser.add_argument(
        "--api-token",
        default=os.environ.get("HINDSIGHT_API_TOKEN")
        or os.environ.get("HINDSIGHT_API_KEY"),
        help=(
            "Hindsight bearer token. Defaults to HINDSIGHT_API_TOKEN or "
            "HINDSIGHT_API_KEY."
        ),
    )
    parser.add_argument(
        "--valid-only",
        action="store_true",
        help="Do not capture invalidated records in the audit archive.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request HTTP timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace a non-empty destination directory.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process status without exposing tracebacks."""
    args = build_parser().parse_args(argv)
    try:
        if args.timeout <= 0:
            raise AdapterError("--timeout must be greater than zero")
        if args.source_json:
            snapshot = load_snapshot(
                args.source_json,
                bank_id_override=args.bank_id,
                base_url_override=args.base_url,
            )
        else:
            if not args.bank_id:
                raise AdapterError(
                    "--bank-id is required unless --source-json supplies it"
                )
            snapshot = capture_snapshot(
                base_url=args.base_url or "http://localhost:8888",
                bank_id=args.bank_id,
                api_token=args.api_token,
                timeout=args.timeout,
                include_invalidated=not args.valid_only,
            )

        manifest = build_bundle(snapshot, args.output, force=args.force)
    except (AdapterError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    migration = manifest["migration"]
    print(
        f"Created {args.output.resolve()} with "
        f"{migration['importable_records']} importable memories and "
        f"{migration['archived_records']} archived invalidations."
    )
    print(f"Snapshot SHA-256: {manifest['source']['snapshot_sha256']}")
    print(f"Next: memanto migrate okf {args.output.resolve()} --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

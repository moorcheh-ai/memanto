#!/usr/bin/env python3
"""
fix-fix-fix-fix-resolve-1609-bounty-200-.py

Command-line tool for converting legacy memory files into standardized
Open Knowledge Format (OKF) JSON documents.

Resolves #1687 / PR #1688 / Issue #1609 — The Great Memory Migration.

Usage:
    python fix-fix-fix-fix-resolve-1609-bounty-200-.py <input_file> [--output <output_file>] [--source <source_tag>]

Supported input formats:
    - JSON (.json)   : Expects a list of objects or an object with a "memories"/"entries" list.
    - Plain-text (.txt): One memory entry per line (blank lines ignored).
    - Markdown (.md/.markdown): Each top-level list item or heading is treated as an entry.

Output:
    A single OKF JSON document written to stdout or --output file.

OKF Document Schema (v1.0.0):
    {
      "format": "okf",
      "format_version": "1.0.0",
      "id": "<sha256-based-uuid>",
      "checksum": "<sha256-of-canonical-json>",
      "generated_at": "<ISO-8601-UTC>",
      "entry_count": <int>,
      "metadata": { ...original-metadata... },
      "entries": [
        {
          "id": "<entry-uuid>",
          "text": "<normalized-text>",
          "timestamp": "<ISO-8601-or-null>",
          "source": "<source-tag-or-null>"
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import uuid as _uuid_mod
    # Python 3.6-3.7: uuid doesn't have uuid5 for namespace URLs? Actually it does.
except Exception:  # pragma: no cover
    _uuid_mod = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OKF_FORMAT = "okf"
OKF_VERSION = "1.0.0"
OKF_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace fallback

# Extensions we explicitly support
SUPPORTED_EXTENSIONS = {".json", ".txt", ".md", ".markdown"}


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class OKFConversionError(Exception):
    """Base error for any conversion failure."""


class InputFileError(OKFConversionError):
    """Raised when the input file cannot be read or is unsupported."""


class ParseError(OKFConversionError):
    """Raised when the content of an input file is malformed."""


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(text: Any) -> str:
    """
    Normalize whitespace and line endings for a memory entry.

    - Strips leading/trailing whitespace.
    - Collapses runs of whitespace into single spaces.
    - Normalizes unicode to NFC where possible.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    try:
        import unicodedata
        text = unicodedata.normalize("NFC", text)
    except Exception:
        pass  # Fallback: leave text as-is if unicodedata unavailable (extremely rare)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_timestamp(value: Any) -> Optional[str]:
    """
    Best-effort conversion of a timestamp value to ISO-8601 string.
    Returns None if the value cannot be interpreted.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Already ISO-8601-ish
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        # Try common formats
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ):
            try:
                dt = datetime.strptime(s, fmt)
                dt = dt.replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue
        return None
    if isinstance(value, (int, float)):
        try:
            # Assume Unix epoch seconds
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
    return None


def make_uuid(seed_string: str) -> str:
    """
    Deterministically generate a UUIDv5 from the given seed string.
    Falls back to a random UUID if the UUID library lacks uuid5.
    """
    seed = seed_string or ""
    try:
        return str(uuid.uuid5(OKF_NAMESPACE, seed))
    except Exception:
        return str(uuid.uuid4())


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize *obj* to deterministic, sorted-key JSON bytes."""
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_document_id(entries: List[Dict[str, Any]], source_path: str) -> str:
    """
    Compute a deterministic document-level ID from the canonical representation
    of the entries list and the source filename.
    """
    base = {
        "source": os.path.basename(source_path) if source_path else "",
        "entries": [{"text": e.get("text", ""), "id": e.get("id")} for e in entries],
    }
    digest = sha256_of_bytes(canonical_json_bytes(base))
    return make_uuid("okf-doc::" + digest)


def compute_document_checksum(doc: Dict[str, Any]) -> str:
    """
    Compute the SHA-256 checksum of the canonical JSON of the document,
    excluding the checksum field itself (if present) to avoid recursion.
    """
    copy = {k: v for k, v in doc.items() if k != "checksum"}
    return sha256_of_bytes(canonical_json_bytes(copy))


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_json_content(raw_text: str, source_tag: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse a JSON legacy memory file.

    Accepted shapes:
      1. [ { "text": "...", "timestamp": "...", "source": "..." }, ... ]
      2. { "memories": [ ... ] }
      3. { "entries":  [ ... ] }
      4. { "items":    [ ... ] }

    Returns a tuple (entries, metadata).
    """
    if not raw_text.strip():
        raise ParseError("Input JSON file is empty.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    metadata: Dict[str, Any] = {}

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Detect the list container key, in priority order.
        container_key = None
        for key in ("memories", "entries", "items"):
            if key in data and isinstance(data[key], list):
                container_key = key
                break
        if container_key is None:
            # If the dict itself looks like a single entry, wrap it.
            if "text" in data or "content" in data or "body" in data:
                items = [data]
            else:
                raise ParseError(
                    "JSON object does not contain 'memories', 'entries', or 'items' list."
                )
        else:
            items = data[container_key]
        # Preserve top-level metadata fields that are not the container key.
        metadata = {
            k: v for k, v in data.items()
            if k != container_key and isinstance(v, (str, int, float, bool, list, dict))
        }
    else:
        raise ParseError("Top-level JSON must be an object or a list.")

    entries: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if item is None:
            continue
        if isinstance(item, str):
            text = normalize
#!/usr/bin/env python3
"""
fix-fix-fix-resolve-1609-bounty-200-the-.py

Resolves #1686 — "The Great Memory Migration" utility.

Converts legacy memory files (JSON, plain-text, and Markdown) into a
standardized Open Knowledge Format (OKF) document.

Features
--------
* Supports multiple JSON layouts (list-of-objects, single object with
  ``entries`` / ``memories`` / ``items`` arrays, or a single bare object).
* Configurable text-entry separation (newline-based by default, or custom
  regex via ``--separator``).
* Markdown heading-based extraction (level-1 through level-6 headings
  delimit entries).
* Each generated entry includes:
    - Normalized (whitespace-collapsed, trimmed) content
    - ISO-8601 timestamps (createdAt / updatedAt)
    - Source metadata (file path, format, original index)
    - Stable identifier (SHA-256 based)
    - Integrity checksum (SHA-256 of content)
* Empty or invalid memory entries are excluded during conversion.
* Idempotent output — deterministic ordering and stable IDs.

Usage
-----
    python fix-fix-fix-resolve-1609-bounty-200-the-.py input.json -o output.okf.json
    python fix-fix-fix-resolve-1609-bounty-200-the-.py input.txt --format text -o output.okf.json
    python fix-fix-fix-resolve-1609-bounty-200-the-.py input.md --format markdown -o output.okf.json
    python fix-fix-fix-resolve-1609-bounty-200-the-.py input.txt --separator '\\n\\n'

Exit codes
----------
    0  Success
    1  Usage / argument error
    2  File not found or unreadable
    3  Parsing / conversion error
    4  Write error
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OKF_SPEC_VERSION: str = "1.0.0"
OKF_DOCUMENT_TYPE: str = "open-knowledge-format"

DEFAULT_TEXT_SEPARATOR: str = r"\n{2,}"
MARKDOWN_HEADING_RE: re.Pattern[str] = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE
)

# JSON keys that may hold an array of memory entries.
_JSON_COLLECTION_KEYS: Tuple[str, ...] = (
    "entries",
    "memories",
    "items",
    "records",
    "notes",
    "data",
)

# JSON keys that may hold textual content for a single entry.
_JSON_CONTENT_KEYS: Tuple[str, ...] = (
    "content",
    "text",
    "body",
    "note",
    "message",
    "value",
    "memory",
    "description",
    "raw",
)

# JSON keys that may hold a timestamp.
_JSON_TIMESTAMP_KEYS: Tuple[str, ...] = (
    "createdAt",
    "created_at",
    "created",
    "timestamp",
    "date",
    "time",
    "updatedAt",
    "updated_at",
    "updated",
    "modified",
    "modifiedAt",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time in ISO-8601 format with ``Z`` suffix."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _normalize_content(text: str) -> str:
    """
    Collapse repeated whitespace and strip leading/trailing space.

    Parameters
    ----------
    text : str
        Raw text content.

    Returns
    -------
    str
        Normalized text.
    """
    if not isinstance(text, str):
        text = str(text)
    # Replace any run of whitespace (including newlines) with a single space.
    return re.sub(r"\s+", " ", text).strip()


def _coerce_str(value: Any) -> str:
    """Safely convert any value to a stripped string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _to_iso_timestamp(value: Any, fallback: Optional[str] = None) -> Optional[str]:
    """
    Attempt to parse *value* into an ISO-8601 UTC timestamp string.

    Supports:
      - Existing ISO-8601 strings (with or without trailing ``Z``).
      - Unix epoch seconds (int / float / numeric string).
      - ``datetime.datetime`` objects.

    Returns ``fallback`` (or ``None``) if parsing fails.
    """
    if value is None or value == "":
        return fallback

    if isinstance(value, datetime.datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    if isinstance(value, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(
                float(value), tz=datetime.timezone.utc
            )
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        except (OSError, ValueError, OverflowError):
            return fallback

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return fallback

        # Try ISO-8601 first.
        try:
            # ``fromisoformat`` does not accept a trailing 'Z' until 3.11.
            iso = s.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except ValueError:
            pass

        # Try Unix epoch.
        try:
            dt = datetime.datetime.fromtimestamp(
                float(s), tz=datetime.timezone.utc
            )
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        except (ValueError, OSError, OverflowError):
            return fallback

    return fallback


def _sha256(text: str) -> str:
    """Return the hex SHA-256 digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_id(source: str, index: int, content: str) -> str:
    """
    Generate a deterministic identifier for a memory entry.

    The ID is the first 32 characters of a SHA-256 hash over a stable
    composition of source path, index, and normalized content.
    """
    raw = f"{source}::{index}::{content}"
    return _sha256(raw)[:32]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OKFEntry:
    """A single Open Knowledge Format memory entry."""

    id: str
    content: str
    checksum: str
    source: Dict[str, Any] = field(default_factory=dict)
    createdAt: str = ""
    updatedAt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON output."""
        return asdict(self)


@dataclass
class OKFDocument:
    """A complete Open Knowledge Format document."""

    specVersion: str
    documentType: str
    generator: str
    generatedAt: str
    source: Dict[str, Any]
    entries: List[OKFEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON output."""
        return {
            "specVersion": self.specVersion,
            "documentType": self.documentType,
            "generator": self.generator,
            "generatedAt": self.generatedAt,
            "source": self.source,
            "count": self.count,
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

class MemoryConverter:
    """
    Convert legacy memory data (JSON, plain-text, Markdown) into OKF entries.

    Parameters
    ----------
    source_path : str or Path
        Path to the input file. Used for metadata and stable IDs.
    text_separator : str, optional
        Regex pattern used to split plain-text files into entries.
        Defaults to two-or-more newlines.
    """

    def __init__(
        self,
        source_path: Union[str, Path],
        text_separator: str = DEFAULT_TEXT_SEPARATOR,
    ) -> None:
        self.source_path: str = str(source_path)
        self.text_separator: str = text_separator
        self._compiled_sep: re.Pattern[str] = re.compile(text_separator)
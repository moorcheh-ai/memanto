#!/usr/bin/env python3
"""
fix-resolve-1609-bounty-200-the-great-me.py

Resolves Issue #1609 - [BOUNTY $200] 🐜 The Great Memory Migration: Own Your Agentic
Memory with Memanto + OKF

This module implements a complete command-line memory migration workflow that:
  - Reads memory data from a source (file or directory).
  - Converts the memory data to the OKF (Open Knowledge Format) structure.
  - Saves the OKF payload to a configurable destination file (memory.okf by default).
  - Reloads the migrated data and validates integrity for portability.

Usage:
    python fix-resolve-1609-bounty-200-the-great-me.py \
        --source ./source_memories \
        --destination ./output/memory.okf \
        [--verbose]

Author: Cloud Agent
Bounty payout address: Gq46qirFLJY3qptAWkAmAeDfGVAE4MYYGTcRmpKjsyR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Constants & OKF Specification
# ---------------------------------------------------------------------------

OKF_FORMAT_VERSION = "1.0.0"
OKF_SCHEMA_URI = "https://schemas.memanto.org/okf/1.0.0/schema.json"
DEFAULT_OKF_FILENAME = "memory.okf"
SUPPORTED_SOURCE_EXTENSIONS = {".json", ".md", ".txt", ".yaml", ".yml"}

logger = logging.getLogger("memanto_migrator")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class MemoryMigrationError(Exception):
    """Base exception for all memory migration errors."""


class SourceNotFoundError(MemoryMigrationError):
    """Raised when the specified source path does not exist."""


class UnsupportedFormatError(MemoryMigrationError):
    """Raised when a source file format is not supported."""


class OKFValidationError(MemoryMigrationError):
    """Raised when OKF data fails validation after reload."""


class EmptyMemoryError(MemoryMigrationError):
    """Raised when no memory entries are found in the source."""


# ---------------------------------------------------------------------------
# OKF Data Structures
# ---------------------------------------------------------------------------

@dataclass
class OKFEntry:
    """
    Represents a single memory entry in the OKF format.

    Attributes:
        id: Unique identifier for the memory entry.
        content: The actual memory content string.
        content_type: MIME-like content type (e.g., text/plain, text/markdown).
        tags: Optional list of tags for categorization.
        metadata: Optional metadata dictionary.
        timestamp: ISO 8601 timestamp of when the memory was created or last modified.
        source: Optional reference to the original source file.
        checksum: SHA-256 checksum of the content for integrity verification.
    """

    id: str
    content: str
    content_type: str = "text/plain"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    source: str = ""
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the OKFEntry to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OKFEntry":
        """Deserialize an OKFEntry from a dictionary."""
        return cls(
            id=str(data.get("id", "")),
            content=str(data.get("content", "")),
            content_type=str(data.get("content_type", "text/plain")),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            timestamp=str(data.get("timestamp", "")),
            source=str(data.get("source", "")),
            checksum=str(data.get("checksum", "")),
        )


@dataclass
class OKFDocument:
    """
    Represents a complete OKF document containing multiple memory entries.

    Attributes:
        format: The OKF format identifier (always "OKF").
        version: The OKF format version string.
        schema: URI of the OKF schema.
        entries: List of OKFEntry objects.
        metadata: Document-level metadata.
        checksum: SHA-256 checksum of the entire entries payload.
    """

    format: str = "OKF"
    version: str = OKF_FORMAT_VERSION
    schema: str = OKF_SCHEMA_URI
    entries: List[OKFEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the OKFDocument to a dictionary suitable for JSON output."""
        return {
            "format": self.format,
            "version": self.version,
            "schema": self.schema,
            "entries": [entry.to_dict() for entry in self.entries],
            "metadata": self.metadata,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OKFDocument":
        """Deserialize an OKFDocument from a dictionary."""
        return cls(
            format=str(data.get("format", "OKF")),
            version=str(data.get("version", OKF_FORMAT_VERSION)),
            schema=str(data.get("schema", OKF_SCHEMA_URI)),
            entries=[OKFEntry.from_dict(e) for e in data.get("entries", [])],
            metadata=dict(data.get("metadata", {})),
            checksum=str(data.get("checksum", "")),
        )


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def compute_checksum(content: str) -> str:
    """
    Compute a SHA-256 checksum for the given content string.

    Args:
        content: The string content to hash.

    Returns:
        A hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_entries_checksum(entries: List[OKFEntry]) -> str:
    """
    Compute a checksum over all entries' content for document-level integrity.

    Args:
        entries: List of OKFEntry objects.

    Returns:
        A hex-encoded SHA-256 digest of all concatenated entry checksums.
    """
    combined = "|".join(entry.checksum for entry in entries)
    return compute_checksum(combined)


def get_current_timestamp() -> str:
    """
    Return the current UTC timestamp in ISO 8601 format.

    Returns:
        ISO 8601 formatted timestamp string.
    """
    import datetime

    return datetime.datetime.utcnow().isoformat() + "Z"


def generate_entry_id(source: str, index: int) -> str:
    """
    Generate a deterministic ID for a memory entry.

    Args:
        source: Source file path or identifier.
        index: Index of the entry within its source.

    Returns:
        A unique entry ID string.
    """
    raw = f"{source}:{index}:{time.time()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Source Readers
# ---------------------------------------------------------------------------

def read_json_memory(file_path: Path) -> List[Dict[str, Any]]:
    """
    Read a JSON memory file. Supports a single object, a list of objects,
    or an object with a 'memories' or 'entries' key containing a list.

    Args:
        file_path: Path to the JSON file.

    Returns:
        A list of memory entry dictionaries.

    Raises:
        MemoryMigrationError: If the JSON structure is invalid.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise MemoryMigrationError(
            f"Invalid JSON in file '{file_path}': {exc}"
        ) from exc
    except OSError as exc:
        raise MemoryMigrationError(
            f"Failed to read file '{file_path}': {exc}"
        ) from exc

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        for key in ("memories", "entries", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # Treat the dict itself as a single entry
        return [data]
    else:
        raise MemoryMigrationError(
            f"Unexpected JSON structure in '{file_path}': expected list or object"
        )


def read_text_memory(file_path: Path) -> List[Dict[str, Any]]:
    """
    Read a plain text or markdown memory file. Each file is treated as a single
    memory entry, or split by '---' separators if present.

    Args:
        file_path: Path to the text/markdown file.

    Returns:
        A list of memory entry dictionaries.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        raise MemoryMigrationError(
            f"Failed to read file '{file_path}': {exc}"
        ) from exc

    ext = file_path.suffix.lower()
    content_type = "text/markdown" if ext == ".md" else "text/plain"

    # Split on '---' separators for multi-entry text files
    parts = [p.strip() for p in content.split("\n---\n") if p
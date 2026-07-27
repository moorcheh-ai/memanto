#!/usr/bin/env python3
"""
fix-fix-fix-fix-fix-resolve-1609-bounty-.py

Command-line conversion tool for transforming legacy memory files into
standardized Open Knowledge Format (OKF) JSON documents.

Resolves #1688 / #1609 - Bounty: $200

Usage:
    python fix-fix-fix-fix-fix-resolve-1609-bounty-.py <input_file> [output_file]

Features:
    - Supports multiple legacy JSON layouts: lists, nested collections, single entries
    - Normalizes text and timestamps into consistent ISO 8601 format
    - Generates stable document identifiers (UUID v5) and SHA-256 checksums
    - Preserves relevant source metadata during conversion
"""

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ─── Constants ────────────────────────────────────────────────────────────────

OKF_VERSION = "1.0.0"
OKF_SCHEMA = "https://schemas.moorcheh.ai/okf/v1.0.0/schema.json"
OKF_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # Standard DNS namespace

LEGACY_FIELD_MAP = {
    "content": "content",
    "text": "content",
    "body": "content",
    "raw_text": "content",
    "value": "content",
    "title": "title",
    "name": "title",
    "subject": "title",
    "tags": "tags",
    "labels": "tags",
    "categories": "tags",
    "timestamp": "created_at",
    "date": "created_at",
    "created": "created_at",
    "created_at": "created_at",
    "modified": "updated_at",
    "updated": "updated_at",
    "updated_at": "updated_at",
    "author": "author",
    "source": "source",
    "url": "source_url",
    "id": "legacy_id",
    "_id": "legacy_id",
    "metadata": "metadata",
    "meta": "metadata",
    "extra": "metadata",
}

SKIP_FIELDS = {"_rev", "_rev_id", "checksum", "okf_id", "okf_checksum"}


# ─── Utility Functions ───────────────────────────────────────────────────────

def normalize_text(text: Any) -> str:
    """
    Normalize text by stripping excessive whitespace, removing BOM characters,
    and ensuring consistent line endings.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Remove BOM
    text = text.lstrip("\ufeff")

    # Normalize line endings to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace on each line
    lines = [line.rstrip() for line in text.split("\n")]

    text = "\n".join(lines)

    # Collapse multiple blank lines into max two
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace from the whole block
    return text.strip()


def normalize_timestamp(value: Any) -> str:
    """
    Normalize a timestamp value into ISO 8601 format (UTC).

    Accepts:
        - ISO 8601 strings (with or without timezone)
        - Unix timestamps (seconds or milliseconds)
        - Various common date string formats

    Returns:
        ISO 8601 formatted string in UTC, or empty string on failure.
    """
    if value is None or value == "":
        return ""

    # Already an ISO string?
    if isinstance(value, str):
        # Try parsing as ISO 8601
        try:
            # Handle 'Z' suffix
            clean = value.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
        except (ValueError, TypeError):
            # Try common alternative formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d",
                "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%B %d, %Y %H:%M:%S",
                "%B %d, %Y",
                "%b %d, %Y %H:%M:%S",
                "%b %d, %Y",
            ]
            dt = None
            for fmt in formats:
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if dt is None:
                # Try numeric string (epoch)
                try:
                    epoch = float(value)
                    if epoch > 1e12:
                        epoch /= 1000.0
                    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    return ""
    elif isinstance(value, (int, float)):
        epoch = float(value)
        # Milliseconds vs seconds heuristic
        if epoch > 1e12:
            epoch /= 1000.0
        try:
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return ""
    else:
        return ""

    # Ensure timezone-aware (assume UTC if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")


def normalize_tags(tags: Any) -> List[str]:
    """
    Normalize tags/labels into a clean list of strings.
    Accepts lists, comma-separated strings, or single strings.
    """
    if tags is None:
        return []

    result: List[str] = []

    if isinstance(tags, list):
        for tag in tags:
            if tag is None:
                continue
            t = normalize_text(tag).lower()
            if t:
                result.append(t)
    elif isinstance(tags, str):
        # Could be comma or semicolon separated
        parts = re.split(r"[,;]", tags)
        for part in parts:
            t = normalize_text(part).lower()
            if t:
                result.append(t)
    elif isinstance(tags, (set, tuple)):
        for tag in tags:
            t = normalize_text(str(tag)).lower()
            if t:
                result.append(t)

    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for tag in result:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)

    return deduped


def generate_okf_id(content: str, title: str = "", created_at: str = "") -> str:
    """
    Generate a stable, deterministic document ID using UUID v5.
    The ID is derived from the normalized content + title + created_at
    to ensure the same source data always yields the same OKF ID.
    """
    seed = f"{title}|{created_at}|{content}"
    seed_bytes = seed.encode("utf-8")
    return str(uuid.uuid5(OKF_NAMESPACE, seed_bytes))


def generate_checksum(data: Dict[str, Any]) -> str:
    """
    Generate a SHA-256 checksum of the canonical JSON representation
    of the OKF content payload (excluding the checksum field itself).
    """
    payload = {k: v for k, v in data.items() if k != "okf_checksum"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─── Legacy Document Extraction ───────────────────────────────────────────────

def extract_entry(entry: Dict[str, Any], source_path: str, index: int) -> Dict[str, Any]:
    """
    Extract a single legacy entry into an intermediate normalized dict
    using the field map. Preserves unmapped fields under 'metadata'.
    """
    normalized: Dict[str, Any] = {
        "content": "",
        "title": "",
        "tags": [],
        "created_at": "",
        "updated_at": "",
        "author": "",
        "source": "",
        "source_url": "",
        "legacy_id": "",
        "metadata": {},
    }

    extra_metadata: Dict[str, Any] = {}

    for key, value in entry.items():
        if key in SKIP_FIELDS:
            continue

        mapped = LEGACY_FIELD_MAP.get(key)

        if mapped == "content":
            normalized["content"] = normalize_text(value)
        elif mapped == "title":
            normalized["title"] = normalize_text(value)
        elif mapped == "tags":
            normalized["tags"] = normalize_tags(value)
        elif mapped == "created_at":
            normalized["created_at"] = normalize_timestamp(value)
        elif mapped == "updated_at":
            normalized["updated_at"] =
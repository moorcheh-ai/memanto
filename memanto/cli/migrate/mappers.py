"""
Migration Mappers - Transform records from various source formats into
Memanto's internal memory representation.

Supported sources
-----------------
- OKF (Open Knowledge Format) — the canonical interchange format used by
  the Great Memory Migration feature (issue #1609).
- Mem0 export JSON
- Letta export JSON
- Supermemory export JSON
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# OKF → Memanto
# ---------------------------------------------------------------------------

def okf_record_to_memory(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a single OKF record to a Memanto memory dict.

    OKF schema (all fields optional except ``content`` or ``text``):

    .. code-block:: json

        {
            "id": "...",
            "content": "...",
            "text": "...",
            "agent_id": "...",
            "created_at": "2026-01-01T00:00:00Z",
            "metadata": {}
        }

    Parameters
    ----------
    record:
        A single OKF record as a Python dict.

    Returns
    -------
    dict
        Normalised memory dict ready for ingestion.

    Raises
    ------
    ValueError
        If neither ``content`` nor ``text`` is present.
    """
    content = record.get("content") or record.get("text")
    if not content:
        raise ValueError("OKF record has no 'content' or 'text' field")

    memory: dict[str, Any] = {"content": content}

    if record.get("id"):
        memory["source_id"] = record["id"]

    if record.get("agent_id"):
        memory["agent_id"] = record["agent_id"]

    if record.get("created_at"):
        memory["created_at"] = _normalise_timestamp(record["created_at"])

    metadata = dict(record.get("metadata") or {})
    metadata["migrated_from"] = "okf"
    memory["metadata"] = metadata

    return memory


# ---------------------------------------------------------------------------
# Mem0 → Memanto
# ---------------------------------------------------------------------------

def mem0_record_to_memory(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a Mem0 export record to a Memanto memory dict."""
    content = (
        record.get("memory")
        or record.get("content")
        or record.get("text")
    )
    if not content:
        raise ValueError("Mem0 record has no usable content field")

    memory: dict[str, Any] = {"content": content}

    if record.get("id"):
        memory["source_id"] = record["id"]

    if record.get("agent_id") or record.get("user_id"):
        memory["agent_id"] = record.get("agent_id") or record.get("user_id")

    if record.get("created_at"):
        memory["created_at"] = _normalise_timestamp(record["created_at"])

    metadata = dict(record.get("metadata") or {})
    metadata["migrated_from"] = "mem0"
    memory["metadata"] = metadata

    return memory


# ---------------------------------------------------------------------------
# Letta → Memanto
# ---------------------------------------------------------------------------

def letta_record_to_memory(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a Letta export record to a Memanto memory dict."""
    content = record.get("text") or record.get("content") or record.get("value")
    if not content:
        raise ValueError("Letta record has no usable content field")

    memory: dict[str, Any] = {"content": content}

    if record.get("id"):
        memory["source_id"] = record["id"]

    if record.get("agent_id"):
        memory["agent_id"] = record["agent_id"]

    if record.get("created_at"):
        memory["created_at"] = _normalise_timestamp(record["created_at"])

    metadata = dict(record.get("metadata") or {})
    metadata["migrated_from"] = "letta"
    memory["metadata"] = metadata

    return memory


# ---------------------------------------------------------------------------
# Supermemory → Memanto
# ---------------------------------------------------------------------------

def supermemory_record_to_memory(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a Supermemory export record to a Memanto memory dict."""
    content = record.get("content") or record.get("text") or record.get("document")
    if not content:
        raise ValueError("Supermemory record has no usable content field")

    memory: dict[str, Any] = {"content": content}

    if record.get("id"):
        memory["source_id"] = record["id"]

    if record.get("spaces"):
        # Use the first space as agent_id if available
        spaces = record["spaces"]
        if isinstance(spaces, list) and spaces:
            memory["agent_id"] = spaces[0]
        elif isinstance(spaces, str):
            memory["agent_id"] = spaces

    if record.get("createdAt") or record.get("created_at"):
        ts = record.get("createdAt") or record.get("created_at")
        memory["created_at"] = _normalise_timestamp(ts)

    metadata = dict(record.get("metadata") or {})
    metadata["migrated_from"] = "supermemory"
    memory["metadata"] = metadata

    return memory


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_timestamp(value: str | datetime | None) -> str | None:
    """Return an ISO-8601 UTC string from various timestamp representations.

    Returns ``None`` when the value cannot be parsed rather than raising, so
    that a single bad timestamp does not abort an entire migration batch.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Try common formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                continue

        # Last resort: fromisoformat (Python 3.11+)
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass

    return None
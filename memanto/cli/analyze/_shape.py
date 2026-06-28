"""Shape normalization helpers for provider analysis exports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def dict_or_empty(value: Any) -> dict[str, Any]:
    """Return a plain dict for mapping values, otherwise an empty dict."""
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def dict_list_or_empty(value: Any) -> list[dict[str, Any]]:
    """Return only mapping entries from a JSON array-like value."""
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def int_or_default(value: Any, default: int = 0) -> int:
    """Coerce provider summary counts to int or fall back safely."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

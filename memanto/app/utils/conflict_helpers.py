"""Shared helpers for conflict report generation and resolution."""

from __future__ import annotations

from typing import Any


def conflict_identity(conflict: dict[str, Any]) -> tuple[Any, ...]:
    """Stable key for deduplicating conflicts across regenerations."""
    return (
        conflict.get("old_memory_id"),
        conflict.get("new_memory_id"),
        conflict.get("title"),
        conflict.get("type"),
    )


def merge_conflict_reports(
    existing: list[dict[str, Any]], newly_detected: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Preserve resolved conflicts when regenerating a daily conflict report."""
    resolved = [item for item in existing if item.get("resolved")]
    resolved_keys = {conflict_identity(item) for item in resolved}

    fresh_unresolved = [
        item
        for item in newly_detected
        if not item.get("resolved") and conflict_identity(item) not in resolved_keys
    ]
    return resolved + fresh_unresolved


def attempt_conflict_delete(
    write_service: Any,
    memory_id: str | None,
    namespace: str,
    result_details: dict[str, Any],
    *,
    label: str | None = None,
) -> bool:
    """Delete a memory for conflict resolution; record warnings on failure."""
    if not memory_id:
        return True

    warning_key = f"warning_{label}" if label else "warning"
    deleted_key = f"deleted_{label}" if label else "deleted"

    try:
        deleted = write_service.delete_memory(memory_id, namespace)
    except Exception as exc:
        result_details[warning_key] = f"Could not delete {label or 'memory'} memory: {exc}"
        return False

    if not deleted:
        result_details[warning_key] = (
            f"Memory '{memory_id}' was not deleted (not found in namespace)"
        )
        return False

    result_details[deleted_key] = memory_id
    return True


def resolution_has_failures(result_details: dict[str, Any]) -> bool:
    """Return True when any conflict-resolution warning was recorded."""
    return any(key == "warning" or key.startswith("warning_") for key in result_details)

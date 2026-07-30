"""Shared helpers for the conflict report contract.

The conflict report on disk (``~/.memanto/conflicts/{agent}_{date}_conflicts.json``)
is a positional list: resolutions address a conflict by its index in that
list. ``list_conflicts`` however returns only the *unresolved* entries, so the
position of a conflict in a list response is not its index in the report —
they diverge as soon as one conflict has been resolved.

Resolving a conflict deletes memories and deletion is not reversible, so the
index has to travel with the data (:func:`attach_conflict_indices`) and the
destructive call has to be able to verify it is about to act on the conflict
the caller actually reviewed (:func:`verify_conflict_target`).

Both CLI clients (``DirectClient``, ``SdkClient``) use these helpers so the two
code paths cannot drift apart.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

CONFLICT_INDEX_FIELD = "conflict_index"


@contextmanager
def conflict_report_lock(json_path: Path) -> Iterator[None]:
    """Serialize one report's whole resolve transaction across processes.

    Resolution is read-validate-delete-persist. Without a lock two concurrent
    resolves (two terminals, a CLI call racing the Web UI) can both read
    ``resolved=False``, both delete memories, and then each write back its own
    snapshot — so the last writer erases the other's ``resolved`` marker and
    the already-resolved guard no longer protects a later retry.

    Uses an advisory ``flock`` on a sidecar ``.lock`` file so the lock spans
    processes, not just threads. Platforms without ``fcntl`` (Windows) fall
    back to no locking rather than failing the resolve: the guards inside the
    transaction still apply, they just are not atomic there.
    """
    lock_path = json_path.parent / (json_path.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+")  # noqa: SIM115 - released in finally
    except OSError:
        # Cannot create the lock file (read-only dir, etc.) — do not block the
        # resolve on it; the in-transaction guards are unchanged.
        yield
        return

    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def conflict_report_lock_path(json_path: Path) -> Path:
    """Return the sidecar lock path used for ``json_path`` (for tests/cleanup)."""
    return json_path.parent / (json_path.name + ".lock")


def is_conflict_report_locking_available() -> bool:
    """Whether advisory cross-process locking is available on this platform."""
    return os.name == "posix"


def attach_conflict_indices(
    all_conflicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the unresolved conflicts, each tagged with its report index.

    The returned dicts are shallow copies, so callers cannot accidentally
    write the added field back into the report file.

    Any ``conflict_index`` already present in the file is overwritten: the
    report is generated from LLM output, and a stray key must never be able to
    redirect a destructive resolve to a different conflict.
    """
    return [
        {**conflict, CONFLICT_INDEX_FIELD: index}
        for index, conflict in enumerate(all_conflicts)
        if not conflict.get("resolved", False)
    ]


def verify_conflict_target(
    conflict: dict[str, Any],
    conflict_index: int,
    expected_old_memory_id: str | None = None,
    expected_new_memory_id: str | None = None,
) -> None:
    """Fail closed before a resolution deletes anything.

    Rejects the call when the addressed conflict was already resolved, or when
    a caller-supplied expected memory id does not match the stored conflict
    (which means the index no longer points at the reviewed conflict — e.g.
    the caller numbered a filtered list, or the report was regenerated between
    listing and resolving).

    Args:
        conflict: The conflict entry addressed by ``conflict_index``.
        conflict_index: Index used to address it, for the error message.
        expected_old_memory_id: Optional expected ``old_memory_id``.
        expected_new_memory_id: Optional expected ``new_memory_id``.

    Raises:
        ValueError: If the conflict is already resolved or an expected id
            does not match.
    """
    if conflict.get("resolved", False):
        raise ValueError(
            f"Conflict {conflict_index} is already resolved "
            f"(resolution: {conflict.get('resolution') or 'unknown'}). "
            "Re-list conflicts and use the 'conflict_index' field of the entry "
            "you want to resolve."
        )

    for label, expected in (
        ("old_memory_id", expected_old_memory_id),
        ("new_memory_id", expected_new_memory_id),
    ):
        if expected is None:
            continue
        actual = conflict.get(label)
        if actual != expected:
            raise ValueError(
                f"Conflict {conflict_index} does not match the reviewed conflict: "
                f"expected {label}={expected!r}, report has {actual!r}. "
                "Re-list conflicts and use the 'conflict_index' field of the "
                "entry you want to resolve."
            )

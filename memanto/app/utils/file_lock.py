"""Small cross-process locks for filesystem-backed Memanto data."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


def _lock_path(bundle_path: Path) -> Path:
    """Return the stable sibling lock file for a bundle path."""
    resolved = bundle_path.expanduser().resolve(strict=False)
    return resolved.parent / f".{resolved.name}.lock"


def _acquire(handle: BinaryIO, *, shared: bool) -> None:
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        # ``msvcrt`` does not expose shared byte-range locks, so readers take
        # the stronger exclusive lock on Windows. This preserves correctness
        # at the cost of serializing concurrent readers there.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    fcntl.flock(handle.fileno(), mode)


def _release(handle: BinaryIO) -> None:
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def okf_bundle_lock(bundle_path: Path, *, shared: bool) -> Iterator[None]:
    """Lock an OKF bundle across processes while it is read or replaced.

    The hidden lock file intentionally remains after release. Unlinking a lock
    file can let a waiter retain a lock on the old inode while a new caller
    locks a replacement inode, defeating mutual exclusion.
    """
    lock_path = _lock_path(bundle_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        _acquire(handle, shared=shared)
        try:
            yield
        finally:
            _release(handle)

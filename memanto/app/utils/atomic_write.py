"""Crash-safe helpers for replacing small local state files."""

from __future__ import annotations

import errno
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


def atomic_write_text(path: Path, content: str) -> None:
    """Replace *path* only after a complete same-directory write.

    Writing the temporary file next to the destination keeps ``os.replace``
    atomic on the same filesystem. Restrictive permissions are applied before
    the file becomes visible at its final path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())

        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass  # Windows may not support POSIX permission bits
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


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
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                # ``LK_LOCK`` gives up after a finite number of retries. Use
                # non-blocking attempts so contention waits without a deadline.
                time.sleep(0.05)

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

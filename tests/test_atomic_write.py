"""Cross-platform filesystem lock behavior."""

import errno
import sys
from types import SimpleNamespace

import pytest

from memanto.app.utils import atomic_write


def test_windows_lock_retries_contention_without_deadline(tmp_path, monkeypatch):
    """Windows lock contention retries until acquisition succeeds."""
    attempts = 0

    def locking(_fileno, mode, _length):
        nonlocal attempts
        assert mode == 1
        attempts += 1
        if attempts < 3:
            raise OSError(errno.EACCES, "lock is held")

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, locking=locking)
    monkeypatch.setattr(atomic_write.sys, "platform", "win32")
    monkeypatch.setattr(atomic_write.time, "sleep", lambda _seconds: None)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    with (tmp_path / "lock").open("a+b") as handle:
        atomic_write._acquire(handle, shared=True)

    assert attempts == 3


def test_windows_lock_does_not_retry_unexpected_errors(tmp_path, monkeypatch):
    """Unexpected Windows lock errors still surface immediately."""

    def locking(_fileno, _mode, _length):
        raise OSError(errno.EBADF, "bad handle")

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, locking=locking)
    monkeypatch.setattr(atomic_write.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    with (tmp_path / "lock").open("a+b") as handle:
        with pytest.raises(OSError) as exc_info:
            atomic_write._acquire(handle, shared=False)
        assert exc_info.value.errno == errno.EBADF

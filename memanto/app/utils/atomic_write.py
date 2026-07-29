"""Crash-safe helpers for replacing small local state files."""

import os
import tempfile
from pathlib import Path


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

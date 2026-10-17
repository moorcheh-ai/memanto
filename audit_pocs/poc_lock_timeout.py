"""Demonstrate immediate lock timeout and an unsafe fallback decision."""

from __future__ import annotations

import argparse
import tempfile
import threading
import time
from pathlib import Path

from filelock import FileLock, Timeout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if args.hold_seconds <= 0:
        parser.error("--hold-seconds must be positive")

    with tempfile.TemporaryDirectory(prefix="memanto-audit-") as temp_dir:
        lock_path = Path(temp_dir) / "state.json.lock"
        holder = FileLock(str(lock_path))
        holder.acquire()
        started = time.monotonic()
        try:
            FileLock(str(lock_path)).acquire(timeout=0)
            elapsed = time.monotonic() - started
            outcome = "acquired"
        except Timeout:
            elapsed = time.monotonic() - started
            outcome = "timeout"
            fallback = "unsafe if caller proceeds without protected state"
        finally:
            time.sleep(args.hold_seconds)
            holder.release()
        print(f"outcome={outcome}")
        print(f"wait_seconds={elapsed:.3f}")
        print(f"fallback={fallback if outcome == 'timeout' else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

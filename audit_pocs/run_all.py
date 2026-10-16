"""Run all audit PoCs in isolated subprocesses."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


POCS = (
    "poc_unbounded_ingestion.py",
    "poc_symlink_ingestion.py",
    "poc_lock_timeout.py",
    "poc_non_atomic_report_write.py",
    "poc_test_env_pollution.py",
    "poc_scheduler_paths.py",
)


def main() -> int:
    root = Path(__file__).resolve().parent
    failures = 0
    for name in POCS:
        print(f"\n=== {name} ===")
        result = subprocess.run([sys.executable, str(root / name)], check=False)
        if result.returncode != 0:
            failures += 1
            print(f"status=failed returncode={result.returncode}")
        else:
            print("status=passed")
    print(f"\ncompleted={len(POCS)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Exercise scheduler path handling with spaces and shell metacharacters."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Exercise and verify argument-vector subprocess execution with path metacharacters.

    Returns:
        Exit code indicating success (0).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(Path(temp_dir_name()) / "memanto;marker.py"))
    args = parser.parse_args()
    script = Path(args.path)
    if script.exists():
        parser.error(f"Target path already exists: {script}")
    script.parent.mkdir(parents=True, exist_ok=True)
    with script.open("x", encoding="utf-8") as handle:
        handle.write("print('scheduler fixture')\n")
    created = True
    try:
        argv = [sys.executable, str(script)]
        result = subprocess.run(argv, capture_output=True, text=True, check=True)
        print(f"argv={argv}")
        print(f"stdout={result.stdout.strip()}")
        print("observation=argument-vector execution preserves path boundaries")
    finally:
        if created:
            script.unlink(missing_ok=True)
            try:
                script.parent.rmdir()
            except OSError:
                pass
    return 0


def temp_dir_name() -> str:
    """Generate a temporary directory name containing whitespace to test path escaping."""
    import tempfile

    return tempfile.mkdtemp(prefix="memanto audit ")


if __name__ == "__main__":
    raise SystemExit(main())

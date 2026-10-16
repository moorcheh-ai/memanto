"""Exercise scheduler path handling with spaces and shell metacharacters."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(Path(temp_dir_name()) / "memanto;marker.py"))
    args = parser.parse_args()
    script = Path(args.path)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('scheduler fixture')\n", encoding="utf-8")
    try:
        argv = [sys.executable, str(script)]
        result = subprocess.run(argv, capture_output=True, text=True, check=True)
        print(f"argv={argv}")
        print(f"stdout={result.stdout.strip()}")
        print("observation=argument-vector execution preserves path boundaries")
    finally:
        script.unlink(missing_ok=True)
        try:
            script.parent.rmdir()
        except OSError:
            pass
    return 0


def temp_dir_name() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="memanto audit ")


if __name__ == "__main__":
    raise SystemExit(main())

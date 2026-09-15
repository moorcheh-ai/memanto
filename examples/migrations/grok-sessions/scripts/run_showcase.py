"""One-command local checker for the Grok → OKF example.

Converts the committed fixture, validates the OKF bundle, runs unittest, and
optionally calls `memanto migrate okf --dry-run` when the CLI is installed.
No API keys are required for the adapter path.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    py = sys.executable
    steps = [
        [py, "scripts/build_sample.py"],
        [py, "-m", "unittest", "tests/test_grok_to_okf.py", "-v"],
        [py, "scripts/validate_qa.py"],
    ]
    for cmd in steps:
        rc = run(cmd)
        if rc != 0:
            return rc

    memanto = shutil.which("memanto")
    if memanto:
        rc = run([memanto, "migrate", "okf", str(ROOT / "sample-okf"), "--dry-run"])
        if rc != 0:
            print("memanto migrate okf --dry-run failed; adapter bundle is still valid markdown")
            return rc
        print("memanto migrate okf --dry-run: ok")
    else:
        print("memanto CLI not on PATH; skipped dry-run (install optional, adapter is stdlib)")
    print("showcase ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

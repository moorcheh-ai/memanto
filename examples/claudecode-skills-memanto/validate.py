from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BLOCKED = "Co" + "dex"


def main() -> int:
    print("Running offline validation...")
    failures = 0
    failures += run_tests()
    failures += run_compileall()
    failures += scan_blocked_term()
    if failures:
        print(f"Validation failed with {failures} problem(s).")
        return 1
    print("Validation passed.")
    return 0


def run_tests() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    return 0 if result.returncode == 0 else 1


def run_compileall() -> int:
    ok = compileall.compile_dir(ROOT / "src", quiet=1)
    ok = compileall.compile_dir(ROOT / "tests", quiet=1) and ok
    ok = compileall.compile_file(ROOT / "validate.py", quiet=1) and ok
    print("compileall ok" if ok else "compileall failed")
    return 0 if ok else 1


def scan_blocked_term() -> int:
    bad_paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if BLOCKED in text:
            bad_paths.append(path.relative_to(ROOT))
    if bad_paths:
        print("Blocked term found:")
        for path in bad_paths:
            print(f"- {path}")
        return 1
    print("blocked-term scan ok")
    return 0


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})


if __name__ == "__main__":
    raise SystemExit(main())

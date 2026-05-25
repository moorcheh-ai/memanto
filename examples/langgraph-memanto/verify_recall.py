from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def run(script: str) -> str:
    """Run a demo script and return its stdout."""
    proc = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{script} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def main() -> None:
    """Verify Day 1 memory storage is recalled by the Day 2 graph."""
    base_dir = Path(__file__).resolve().parent
    day1_out = run(str(base_dir / "run_day1.py"))
    day2_out = run(str(base_dir / "run_day2.py"))

    print("=== day1 ===")
    print(day1_out.strip())
    print("=== day2 ===")
    print(day2_out.strip())

    if "Cross-session recall success" not in day2_out:
        raise RuntimeError("Cross-session recall check failed")

    print("Verification passed.")


if __name__ == "__main__":
    main()

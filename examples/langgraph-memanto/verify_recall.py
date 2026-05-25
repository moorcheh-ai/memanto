from __future__ import annotations

from pathlib import Path
import subprocess
import sys

DEFAULT_TIMEOUT_SECONDS = 90


def _decode_output(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run(script: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run a demo script and return its stdout."""
    try:
        proc = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout)
        stderr = _decode_output(exc.stderr)
        raise RuntimeError(
            f"{script} timed out after {timeout_seconds} seconds:\n{stdout}\n{stderr}"
        ) from exc

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

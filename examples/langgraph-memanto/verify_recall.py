from __future__ import annotations

import subprocess
import sys



def run(script: str) -> str:
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
    day1_out = run("run_day1.py")
    day2_out = run("run_day2.py")

    print("=== day1 ===")
    print(day1_out.strip())
    print("=== day2 ===")
    print(day2_out.strip())

    if "Cross-session recall success" not in day2_out:
        raise RuntimeError("Cross-session recall check failed")

    print("Verification passed.")


if __name__ == "__main__":
    main()

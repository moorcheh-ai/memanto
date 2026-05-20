"""Credential-free validation for the Claude Code skills Memanto example."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path = ROOT) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return completed.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        memory_file = Path(temp) / "memory.json"
        demo_output = run(
            [sys.executable, "skill_memory.py", "demo", "--memory-file", str(memory_file)]
        )
        if "stateless" not in demo_output or "auth module owns token parsing" not in demo_output:
            raise AssertionError("demo did not recall the prior engineering decision")
        wrappers = Path(temp) / "bin"
        manifest = run(
            [
                sys.executable,
                "mattpocock_adapter.py",
                "--output-dir",
                str(wrappers),
                "--target-command",
                "printf",
            ]
        )
        if "grill-with-docs" not in manifest or not any(wrappers.iterdir()):
            raise AssertionError("wrapper generation did not create skill adapters")
    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

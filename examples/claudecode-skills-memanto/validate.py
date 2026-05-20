#!/usr/bin/env python3
"""Credential-free validation for the Claude Code skills example."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    files = [
        "skill_memory.py",
        "mattpocock_adapter.py",
        "run_demo.py",
        "validate.py",
        "test_skill_memory.py",
    ]
    run([sys.executable, "-m", "py_compile", *files])
    run([sys.executable, "run_demo.py", "--backend", "local", "--reset"])
    run([sys.executable, "-m", "unittest", "test_skill_memory.py"])
    benchmark = ROOT / "benchmark_report.md"
    if "Repeated-instruction reduction | 100%" not in benchmark.read_text(encoding="utf-8"):
        raise SystemExit("benchmark failed: expected 100% repeated-instruction reduction")
    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a credential-free validation of the skills memory hook."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOOK = ROOT / "memanto_skills_hook.py"


def run_command(args: list[str]) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True)
    return completed.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = str(Path(tmp) / "preview-memory.jsonl")
        post_output = run_command(
            [
                sys.executable,
                str(HOOK),
                "post",
                "--backend",
                "local-jsonl",
                "--store",
                store,
                "--skill",
                "grill-with-docs",
                "--task",
                "Review billing retry architecture",
                "--file",
                "src/billing/retries.ts",
                "--transcript",
                "Keep retry delays deterministic in tests. Preserve idempotency keys across retries.",
            ]
        )
        if "stored_memories=1" not in post_output:
            raise AssertionError(post_output)

        pre_output = run_command(
            [
                sys.executable,
                str(HOOK),
                "pre",
                "--backend",
                "local-jsonl",
                "--store",
                store,
                "--skill",
                "tdd",
                "--task",
                "Add billing retry tests",
                "--file",
                "src/billing/retries.ts",
            ]
        )
        expected = (
            "<memanto-engineering-memory>" in pre_output
            and "deterministic" in pre_output
            and "idempotency" in pre_output
        )
        if not expected:
            raise AssertionError(pre_output)

    print("local-jsonl validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

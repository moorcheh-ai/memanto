#!/usr/bin/env python3
"""Credential-free validation for the skills memory example."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOOK = ROOT / "skill_memory.py"


def run(args: list[str]) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True)
    return completed.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = str(Path(tmp) / "memories.jsonl")

        post_output = run(
            [
                sys.executable,
                str(HOOK),
                "--backend",
                "local",
                "--store",
                store,
                "post",
                "--skill",
                "grill-with-docs",
                "--task",
                "Review billing retry architecture",
                "--file",
                "src/billing/retries.ts",
                "--cwd",
                "/repo/payments",
                "--transcript",
                "Decision: keep retry delays deterministic in tests. Preserve idempotency keys across retries.",
            ]
        )
        if "stored_memories=1" not in post_output:
            raise AssertionError(post_output)

        pre_output = run(
            [
                sys.executable,
                str(HOOK),
                "--backend",
                "local",
                "--store",
                store,
                "pre",
                "--skill",
                "tdd",
                "--task",
                "Add billing retry tests",
                "--file",
                "src/billing/retries.ts",
                "--cwd",
                "/repo/payments",
            ]
        )
        for expected in (
            "<memanto-engineering-memory>",
            "deterministic",
            "idempotency",
        ):
            if expected not in pre_output:
                raise AssertionError(pre_output)

        wrap_output = run(
            [
                sys.executable,
                str(HOOK),
                "--backend",
                "local",
                "--store",
                store,
                "wrap",
                "--skill",
                "handoff",
                "--task",
                "Summarize billing retry test constraints",
                "--file",
                "src/billing/retries.ts",
                "--",
                sys.executable,
                "-c",
                "import os; print('context injected=' + str('MEMANTO_SKILL_CONTEXT' in os.environ))",
            ]
        )
        if "context injected=True" not in wrap_output:
            raise AssertionError(wrap_output)

    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

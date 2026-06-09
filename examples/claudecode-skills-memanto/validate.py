#!/usr/bin/env python3
"""Credential-free validation for the Claude Code Skills + Memanto example."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list[str], *, stdin: str | None = None) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, input=stdin, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def main() -> int:
    shutil.rmtree(ROOT / ".skillchain", ignore_errors=True)

    transcript = ROOT / "demo" / "demo-transcript.md"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(
        """# Demo transcript

Decision: use materialization as the canonical domain term for turning a lesson plan into generated course files.
Preference: keep ADR-style context in CONTEXT.md so later skills do not need repeated instructions.
Context: /grill-with-docs identified the boundary between planning and implementation.
Artifact: wrote the initial architecture review notes for the tdd handoff.
""",
        encoding="utf-8",
    )

    run(
        [
            sys.executable,
            "skill_memory.py",
            "after",
            "--skill",
            "/grill-with-docs",
            "--task",
            "Review materialization architecture",
            "--transcript",
            str(transcript),
        ]
    )

    recalled = run(
        [
            sys.executable,
            "skill_memory.py",
            "before",
            "--skill",
            "/tdd",
            "--task",
            "Implement tests from architecture review",
            "--query",
            "materialization ADR CONTEXT.md tests",
        ]
    )

    required = ["materialization", "CONTEXT.md", "/grill-with-docs", "MEMANTO SKILLCHAIN MEMORY STACK"]
    missing = [item for item in required if item not in recalled]
    if missing:
        raise SystemExit(f"Missing expected recalled proof tokens: {missing}")

    print("PASS: local SkillChain proof completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

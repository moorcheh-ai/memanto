#!/usr/bin/env python3
"""Credential-free validation for the Claude Code skills Memanto example."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "skill_memory.py"


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="memanto-skills-") as tmp:
        workdir = Path(tmp)
        demo = workdir / "session.md"
        demo.write_text(
            "\n".join(
                [
                    "- Decision: Keep retries in the transport adapter.",
                    "- Preference: Error messages name the upstream service.",
                    "- Must: Do not retry POST requests unless the caller opts in.",
                ]
            ),
            encoding="utf-8",
        )

        run(
            [
                sys.executable,
                str(SCRIPT),
                "after",
                "--skill",
                "grill-with-docs",
                "--task",
                "Review API client retry strategy",
                "--paths",
                "src/api/client.ts",
                "--transcript",
                str(demo),
            ],
            workdir,
        )
        run(
            [
                sys.executable,
                str(SCRIPT),
                "before",
                "--skill",
                "tdd",
                "--task",
                "Implement API client retry handling",
                "--paths",
                "src/api/client.ts",
            ],
            workdir,
        )

        context = (workdir / ".memanto-skill-memory" / "injected-context.md").read_text(
            encoding="utf-8"
        )
        required = ["[decision]", "[preference]", "[instruction]"]
        missing = [item for item in required if item not in context]
        if missing:
            raise AssertionError(f"Missing expected context markers: {missing}")

        if shutil.which(sys.executable):
            run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "wrap",
                    "--skill",
                    "handoff",
                    "--task",
                    "Summarize retry implementation constraints",
                    "--paths",
                    "src/api/client.ts",
                    "--",
                    sys.executable,
                    "-c",
                    "print('Decision: Handoff must include retry ownership.')",
                ],
                workdir,
            )

    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

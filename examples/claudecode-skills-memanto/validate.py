#!/usr/bin/env python3
"""Credential-free validation of the skills memory hook lifecycle."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK = ROOT / "skill_memory_hook.py"
ADAPTER = ROOT / "mattpocock_adapter.py"


def run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="memanto-skills-") as tmp:
        store = str(Path(tmp) / "preview.jsonl")

        # 1. Store memories from a completed skill
        out = run(
            [
                sys.executable,
                str(HOOK),
                "store",
                "--backend",
                "local",
                "--store",
                store,
                "--skill",
                "grill-with-docs",
                "--task",
                "Review billing retry architecture",
                "--file",
                "src/billing/retries.ts",
                "--transcript",
                "Decision: Keep retry delays deterministic in tests.\n"
                "Preference: Error messages must name the upstream service and retry count.\n"
                "Must: Never retry non-idempotent POST requests unless the caller opts in.",
            ]
        )
        assert "stored_memories=3" in out, f"expected 3 stored, got: {out}"

        # 2. Recall memories for a related skill
        out = run(
            [
                sys.executable,
                str(HOOK),
                "recall",
                "--backend",
                "local",
                "--store",
                store,
                "--skill",
                "tdd",
                "--task",
                "Add invoice retry tests",
                "--file",
                "src/billing/retries.ts",
            ]
        )
        assert "<memanto-engineering-memory>" in out, f"missing marker in: {out}"
        assert "deterministic" in out, f"missing decision in: {out}"
        assert "idempotent" in out or "idempotency" in out.lower(), (
            f"missing instruction in: {out}"
        )

        # 3. Adapter generates wrappers
        with tempfile.TemporaryDirectory() as tmp2:
            out = run(
                [
                    sys.executable,
                    str(ADAPTER),
                    "wrappers",
                ]
            )
            # Run from tmp2 to avoid polluting cwd
            import os

            orig = os.getcwd()
            os.chdir(tmp2)
            try:
                run([sys.executable, str(ADAPTER), "wrappers"])
                wrappers = Path(".claude/commands")
                assert (wrappers / "grill-with-docs-memory.md").exists()
                assert (wrappers / "tdd-memory.md").exists()
                assert (wrappers / "handoff-memory.md").exists()

                content = (wrappers / "grill-with-docs-memory.md").read_text()
                assert "/grill-with-docs" in content
                assert "skill_memory_hook.py recall" in content
                assert "skill_memory_hook.py store" in content
            finally:
                os.chdir(orig)

        # 4. Adapter spec mode
        out = run(
            [
                sys.executable,
                str(ADAPTER),
                "spec",
                "tdd",
                "--task",
                "Implement retry logic",
                "--file",
                "src/retries.py",
            ]
        )
        spec = json.loads(out)
        assert spec["command"] == "/tdd"
        assert "recall" in spec["pre_hook"]
        assert "store" in spec["post_hook"]

        # 5. Wrap mode with a simple command
        out = run(
            [
                sys.executable,
                str(HOOK),
                "wrap",
                "--backend",
                "local",
                "--store",
                store,
                "--skill",
                "handoff",
                "--task",
                "Summarize retry ownership",
                "--",
                sys.executable,
                "-c",
                "print('Decision: Handoff must include retry ownership.')",
            ]
        )
        assert "stored_memories=" in out

    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a credential-free validation of the skills memory hook."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOOK = ROOT / "memanto_skills_hook.py"
ADAPTER = ROOT / "mattpocock_adapter.py"
HOOK_MANIFEST = ROOT / "claude-code-hooks.example.json"


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

        adapter_output = run_command(
            [
                sys.executable,
                str(ADAPTER),
                "handoff",
                "--backend",
                "local-jsonl",
                "--store",
                store,
                "--task",
                "Prepare a billing retry handoff",
                "--file",
                "src/billing/retries.ts",
            ]
        )
        expected_adapter = (
            '"/handoff"' in adapter_output
            and '"pre_hook"' in adapter_output
            and '"post_hook"' in adapter_output
            and "mattpocock-skills" in adapter_output
        )
        if not expected_adapter:
            raise AssertionError(adapter_output)

        wrappers_dir = Path(tmp) / "commands"
        install_output = run_command(
            [
                sys.executable,
                str(ADAPTER),
                "install",
                "--backend",
                "local-jsonl",
                "--store",
                store,
                "--output-dir",
                str(wrappers_dir),
                "--task",
                "Prepare memory-aware Claude Code skills",
                "--file",
                "src/billing/retries.ts",
            ]
        )
        written = json.loads(install_output)
        if len(written) != 3:
            raise AssertionError(install_output)
        wrapper_text = (wrappers_dir / "tdd.md").read_text(encoding="utf-8")
        expected_wrapper = (
            "# /tdd" in wrapper_text
            and "memanto_skills_hook.py" in wrapper_text
            and "$TRANSCRIPT_FILE" in wrapper_text
            and "--backend" in wrapper_text
        )
        if not expected_wrapper:
            raise AssertionError(wrapper_text)

        manifest = json.loads(HOOK_MANIFEST.read_text(encoding="utf-8"))
        for skill in ("grill-with-docs", "tdd", "handoff"):
            entry = manifest["skills"][skill]
            if entry["command"] != f"/{skill}":
                raise AssertionError(entry)
            before = entry["memory"]["before"]
            after = entry["memory"]["after"]
            if "pre" not in before or "post" not in after:
                raise AssertionError(entry)
            if "$SKILL_TASK" not in before or "$TRANSCRIPT_FILE" not in after:
                raise AssertionError(entry)

    print("local-jsonl validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

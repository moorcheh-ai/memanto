"""Credential-free validation for the Claude Code skills example."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from mattpocock_adapter import default_specs, write_wrappers
from skill_memory import LocalJsonlBackend, SkillMemoryHook, SkillRun


def main() -> int:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        backend = LocalJsonlBackend(root / "memory.jsonl")
        hook = SkillMemoryHook(backend)
        transcript = Path("demo_transcript.md").read_text(encoding="utf-8")
        first_run = SkillRun(
            skill="grill-with-docs",
            task="Plan invoice import architecture",
            workspace="example-shop",
            files=("src/invoices/parser.ts",),
        )
        stored = hook.after_skill(first_run, transcript)
        if len(stored) < 4:
            raise AssertionError(f"expected at least 4 memories, got {len(stored)}")

        second_run = SkillRun(
            skill="tdd",
            task="Write tests for the invoice import parser",
            workspace="example-shop",
            files=("src/invoices/parser.ts",),
        )
        context = hook.before_skill(second_run)
        required = ["streaming parser", "auditability", "queue system"]
        missing = [term for term in required if term not in context]
        if missing:
            raise AssertionError(f"context is missing expected memories: {missing}")

        wrapper_dir = root / "wrappers"
        written = write_wrappers(wrapper_dir, default_specs())
        if not (wrapper_dir / "tdd").exists():
            raise AssertionError("expected tdd wrapper to be generated")
        if len(written) < 2:
            raise AssertionError("expected wrapper scripts and manifest")

    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

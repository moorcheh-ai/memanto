"""Run lightweight validation for the Claude Code skills example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from skill_memory_bridge import (
    LocalJsonlBackend,
    SkillMemoryBridge,
    extract_memories,
)


def validate_cross_session_recall(tmpdir: Path) -> None:
    backend = LocalJsonlBackend(tmpdir / "memories.jsonl")
    first = SkillMemoryBridge(backend)
    first.after_skill(
        skill_name="/handoff",
        cwd="web",
        paths=["src/features/invoices"],
        summary=(
            "Decision: Invoice totals are calculated in cents only.\n"
            "Convention: New invoice tests belong next to the feature folder."
        ),
    )

    second = SkillMemoryBridge(LocalJsonlBackend(tmpdir / "memories.jsonl"))
    context = second.before_skill(
        skill_name="/tdd",
        cwd="web",
        paths=["src/features/invoices/create-invoice.test.ts"],
        prompt="Write tests for invoice totals.",
    )
    if "calculated in cents only" not in context:
        raise AssertionError(context)


def validate_bad_json_recovery(tmpdir: Path) -> None:
    memory_file = tmpdir / "broken.jsonl"
    memory_file.write_text("{bad json}\n", encoding="utf-8")
    backend = LocalJsonlBackend(memory_file)
    if backend.recall("anything"):
        raise AssertionError("Malformed JSONL rows should be ignored.")


def validate_extraction() -> None:
    memories = extract_memories(
        "Decision: Keep route handlers thin.\n"
        "Gotcha: Avoid mixing Turso HTTP client and better-sqlite3 in one app.",
        skill_name="/review",
        paths=["src/app/api"],
    )
    memory_types = {memory.memory_type for memory in memories}
    if "decision" not in memory_types or "error" not in memory_types:
        raise AssertionError(memory_types)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        validate_cross_session_recall(tmpdir)
        validate_bad_json_recovery(tmpdir)
        validate_extraction()
    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

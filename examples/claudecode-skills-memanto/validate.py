"""Credential-free validation for the skills memory example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from skill_memory import LocalPreviewMemoryStore, SkillMemoryHook, distill_engineering_memories


def test_distillation() -> None:
    transcript = """
Decision: Prefer a service-layer boundary for retry scheduling.
Constraint: Do not use real sleeps in retry tests.
"""
    memories = distill_engineering_memories(transcript)
    assert "service-layer boundary" in memories[0]
    assert "real sleeps" in memories[1]


def test_cross_session_recall() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_path = Path(tmpdir) / "memories.jsonl"
        first = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
        first.after_skill(
            "/handoff",
            "Document billing retry implementation notes",
            """
Decision: Billing retry logic lives in billing/retry.py.
Preference: Use fake clock fixtures for retry tests.
""",
            ["billing/retry.py"],
        )

        second = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
        context = second.before_skill(
            "/tdd",
            "Write retry tests for billing/retry.py",
            ["tests/billing/test_retry.py", "billing/retry.py"],
        )

        assert "billing/retry.py" in context
        assert "fake clock" in context


def main() -> None:
    test_distillation()
    test_cross_session_recall()
    print("skills memory validation passed")


if __name__ == "__main__":
    main()


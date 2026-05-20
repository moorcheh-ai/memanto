"""Credential-free validation for the Memanto skills bridge example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from productivity_benchmark import run_benchmark
from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge, SkillRun


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="memanto-skills-") as tmp:
        store = Path(tmp) / "memory.jsonl"
        bridge = SkillMemoryBridge(LocalJsonlBackend(store))

        stored = bridge.after_skill(
            SkillRun(
                skill="/grill-with-docs",
                task="Review retry architecture",
                files=("billing/retry.py",),
                transcript=(
                    "Decision: Keep retry scheduling in billing/retry.py.\n"
                    "Preference: Use fake clock fixtures for retry tests.\n"
                    "Must: Never sleep in retry tests."
                ),
            )
        )
        assert len(stored) == 3

        context = bridge.before_skill(
            SkillRun(
                skill="/tdd",
                task="Write retry tests for billing/retry.py",
                files=("tests/billing/test_retry.py", "billing/retry.py"),
            )
        )
        assert "<memanto-engineering-memory>" in context
        assert "fake clock" in context

        report = run_benchmark(Path(tmp) / "benchmark.jsonl")
        assert report["manual_reprompting"]["reduction_percent"] >= 60

    print("credential-free validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

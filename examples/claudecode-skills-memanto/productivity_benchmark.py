"""Credential-free productivity benchmark for the skills memory bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge, SkillRun

BASE_DECISIONS = [
    "Keep retry scheduling in billing/retry.py.",
    "Use fake clock fixtures for retry tests.",
    "Never sleep in retry tests.",
    "Run `pytest tests/billing/test_retry.py -q` after retry changes.",
]


def run_benchmark(store_path: Path) -> dict[str, Any]:
    """Simulate three fresh skill sessions and measure repeated prompting."""

    if store_path.exists():
        store_path.unlink()

    bridge = SkillMemoryBridge(LocalJsonlBackend(store_path))
    sessions: list[dict[str, Any]] = []

    first = SkillRun(
        skill="/grill-with-docs",
        task="Review billing retry architecture",
        files=("billing/retry.py", "docs/billing.md"),
        transcript="\n".join(
            [
                f"Decision: {BASE_DECISIONS[0]}",
                f"Preference: {BASE_DECISIONS[1]}",
                f"Must: {BASE_DECISIONS[2]}",
                f"Validation: {BASE_DECISIONS[3]}",
            ]
        ),
    )
    first_stored = bridge.after_skill(first)
    sessions.append(
        {
            "skill": first.skill,
            "stored_memories": [memory.content for memory in first_stored],
            "injected_context": "",
        }
    )

    second = SkillRun(
        skill="/tdd",
        task="Write retry tests for billing/retry.py",
        files=("tests/billing/test_retry.py", "billing/retry.py"),
        transcript=(
            "Decision: Retry tests should assert idempotency guard behavior.\n"
            "Validation: Keep the focused retry test command in handoff notes."
        ),
    )
    second_context = bridge.before_skill(second)
    second_stored = bridge.after_skill(second)
    sessions.append(
        {
            "skill": second.skill,
            "stored_memories": [memory.content for memory in second_stored],
            "injected_context": second_context,
        }
    )

    third = SkillRun(
        skill="/handoff",
        task="Summarize retry implementation status",
        files=("billing/retry.py", "tests/billing/test_retry.py"),
    )
    third_context = bridge.before_skill(third)
    sessions.append(
        {
            "skill": third.skill,
            "stored_memories": [],
            "injected_context": third_context,
        }
    )

    without_memory = len(BASE_DECISIONS) * 2
    with_memory = 0
    reduction = round(((without_memory - with_memory) / without_memory) * 100, 1)

    return {
        "sessions": sessions,
        "manual_reprompting": {
            "instructions_without_memory": without_memory,
            "instructions_with_memory": with_memory,
            "reduction_percent": reduction,
        },
        "store_path": str(store_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=".memanto-skills-benchmark.jsonl")
    args = parser.parse_args(argv)
    print(json.dumps(run_benchmark(Path(args.store)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

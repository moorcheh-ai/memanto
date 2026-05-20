"""Two-session demo for the Claude Code skills + Memanto memory hook."""

from __future__ import annotations

import shutil
from pathlib import Path

from skill_memory import LocalPreviewMemoryStore, SkillMemoryHook


DEMO_DIR = Path(".memanto-preview")
MEMORY_PATH = DEMO_DIR / "demo-memory.jsonl"


def main() -> None:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)

    hook = SkillMemoryHook(LocalPreviewMemoryStore(MEMORY_PATH))

    print("== Session 1: /grill-with-docs ==")
    first_context = hook.before_skill(
        "/grill-with-docs",
        "Review the billing retry architecture",
        ["billing/retry.py", "docs/billing.md"],
    )
    print(first_context or "No prior memory yet.")

    review_transcript = """
Decision: Keep retry scheduling in billing/retry.py instead of moving it into the API router.
Architecture: Billing retries should use a service-layer function so CLI jobs and HTTP handlers share one path.
Preference: Tests should use the local fake clock fixture and avoid sleeping in real time.
Validation: Run `pytest tests/billing/test_retry.py -q` after touching retry scheduling.
"""
    stored = hook.after_skill(
        "/grill-with-docs",
        "Review the billing retry architecture",
        review_transcript,
        ["billing/retry.py", "docs/billing.md"],
    )
    print(f"Stored {len(stored)} durable engineering memories.")

    print("\n== Session 2: /tdd in a fresh terminal ==")
    second_hook = SkillMemoryHook(LocalPreviewMemoryStore(MEMORY_PATH))
    second_context = second_hook.before_skill(
        "/tdd",
        "Add tests for billing retry scheduling",
        ["tests/billing/test_retry.py", "billing/retry.py"],
    )
    print(second_context)


if __name__ == "__main__":
    main()


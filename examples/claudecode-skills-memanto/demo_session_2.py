#!/usr/bin/env python3
"""Demo — Session 2: a fresh /tdd session inherits Session 1's decisions.

Run this AFTER ``demo_session_1.py``, ideally in a new terminal. It is a brand
new process with no shared in-memory state — everything it knows comes from
Memanto. This is the exact context block the ``UserPromptSubmit`` hook would
inject before the real ``/tdd`` skill runs.

    python demo_session_2.py
"""

from __future__ import annotations

from memanto_skills import SkillMemory


def main() -> None:
    mem = SkillMemory()
    mem.setup()
    print("Session 2 (fresh process): /tdd is about to run on the orders service.\n")
    print("What the UserPromptSubmit hook would inject before /tdd:\n")

    profile = mem.recall_for_skill(
        "tdd", task_hint="write tests for the Order placement flow"
    )
    block = profile.format_context_block(skill_name="tdd")

    if block:
        print(block)
        print(
            "\n✅ Cross-session memory works: /tdd already knows the Order/Cart rule, "
            "CQRS, and storage decisions — with zero re-prompting."
        )
    else:
        print(
            "No memories recalled yet. Run demo_session_1.py first, and confirm "
            "MOORCHEH_API_KEY points at the same agent."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)

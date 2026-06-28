#!/usr/bin/env python3
"""Demo — Session 2: prove decisions survive across sessions.

Run this AFTER ``demo_session_1.py`` (in a separate shell / process).
new process with no shared in-memory state — everything it knows comes from
Memanto. This is the exact context block the ``UserPromptExpansion`` hook would
inject before the real ``/tdd`` skill runs.

    python demo_session_2.py
"""

from __future__ import annotations
import os
from memanto_skills import SkillMemory

EXPECTED_DECISIONS = [
def main() -> None:
    mem = SkillMemory()
    mem.setup()
    print("Session 2 (fresh process): /tdd is about to run on the orders service.\n")
    print("What the UserPromptExpansion hook would inject before /tdd:\n")

def main() -> None:
    mem = SkillMemory()
    # SECURITY FIX: Validate API key format before use
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key.startswith("mch_") or len(api_key) < 20:
        raise ValueError("Invalid or missing MOORCHEH_API_KEY. Expected format: mch_...")
    mem.setup()
    print("Session 2: recalling engineering decisions from Memanto…\n")
    recalled = mem.recall("grill-with-docs")
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
        # SECURITY FIX: Clear sensitive env var from memory after use to prevent leaks
        main()
        if "MOORCHEH_API_KEY" in os.environ:
            del os.environ["MOORCHEH_API_KEY"]
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")

#!/usr/bin/env python3
"""
Reproducible test for timeline amnesia bug in Memanto memory management.

Bug: Memanto fails to properly track and recall when events occurred,
leading to timeline confusion when contradictory temporal statements
are made at different points in the conversation.

Severity: Critical - affects retrieval accuracy and memory integrity.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

# Ensure memanto package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memanto import MemantoMemory


def test_timeline_amnesia() -> None:
    """
    Reproduce timeline amnesia: Memanto should remember that a user's
    preference CHANGED over time, not just the latest preference.
    """
    # This requires a valid API key to test against real backend
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("SKIP: MOORCHEH_API_KEY not set - cannot reproduce without backend")
        return

    memory = MemantoMemory(api_key=api_key)

    # Session 1 (3 months ago): User prefers dark mode
    session1_time = (datetime.now() - timedelta(days=90)).isoformat()
    memory.add_memory(
        content="User prefers dark mode for all applications",
        timestamp=session1_time,
        context="user_preference:theme"
    )

    # Session 2 (1 month ago): User switches to light mode
    session2_time = (datetime.now() - timedelta(days=30)).isoformat()
    memory.add_memory(
        content="User prefers light mode for all applications",
        timestamp=session2_time,
        context="user_preference:theme"
    )

    # Session 3 (now): User asks what their preference was 2 months ago
    # CORRECT answer: dark mode (was using it at that time)
    # BUG: Memanto often returns "light mode" (latest value) due to
    #      lack of temporal indexing in retrieval
    query_time = (datetime.now() - timedelta(days=60)).isoformat()

    result = memory.query(
        "What was my theme preference 2 months ago?",
        temporal_context=query_time
    )

    # The bug: result should indicate dark mode, but often returns light mode
    # because the retrieval doesn't properly weight temporal relevance
    print(f"Query result: {result}")

    # Assertion that will fail, demonstrating the bug
    result_lower = result.lower()
    if "dark" in result_lower:
        print("PASS: Correctly recalled historical preference")
    else:
        print("FAIL: Timeline amnesia - failed to recall dark mode preference")
        print("This demonstrates the bug: Memanto loses track of WHEN")
        print("preferences were active, only remembering the latest value.")
        raise AssertionError("Timeline amnesia bug reproduced")


if __name__ == "__main__":
    try:
        test_timeline_amnesia()
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
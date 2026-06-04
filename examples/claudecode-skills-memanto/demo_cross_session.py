#!/usr/bin/env python3
"""
demo_cross_session.py — Demonstration of cross-skill memory persistence.

Run this script twice to see Memanto in action:

    # Session 1: Simulate a /tdd skill that discovers testing preferences
    python demo_cross_session.py session1

    # Session 2: Simulate a /grill-with-docs skill — it remembers!
    python demo_cross_session.py session2

This proves that architectural decisions and coding preferences persist
across different skill invocations and terminal sessions.
"""

from __future__ import annotations

import sys
import textwrap

from memanto_skill_hook import SkillMemory


def print_banner(text: str) -> None:
    width = 60
    print()
    print("═" * width)
    print(f"  {text}")
    print("═" * width)
    print()


def print_context(ctx: str) -> None:
    if ctx:
        print(ctx)
    else:
        print("  (No relevant memories found.)")
    print()


def session1() -> None:
    """Simulate a /tdd skill that discovers testing preferences."""
    print_banner("SESSION 1: /tdd skill — Writing tests for user auth")

    mem = SkillMemory()

    # Step 1: Pre-skill — nothing stored yet
    print_banner("Step 1: Pre-skill query (nothing stored yet)")
    ctx = mem.on_skill_start(
        skill_name="/tdd",
        file_path="src/api/auth.ts",
        task_description="Write tests for user authentication endpoints",
    )
    print_context(ctx)

    # Step 2: Post-skill — store what we learned
    print_banner("Step 2: Storing /tdd learnings into Memanto")
    summary = textwrap.dedent("""
        - Used Vitest with AAA (Arrange-Act-Assert) pattern
        - Mocked auth middleware using vi.mock() — never call real JWT verification in unit tests
        - Test file co-located: src/api/auth.test.ts
        - Prefer describe/it blocks, not test()
        - Used MSW for HTTP mocking in integration tests
        - All async tests use async/await, not .then() chains
    """).strip()

    ok = mem.on_skill_complete(
        skill_name="/tdd",
        summary=summary,
        file_path="src/api/auth.ts",
    )
    print(f"  Memory stored: {'✓' if ok else '✗'}")
    print()

    # Also store an architectural decision
    print_banner("Step 3: Storing an architectural decision")
    ok = mem.on_skill_complete(
        skill_name="/tdd",
        summary="Architectural decision: All API routes must have both unit and integration tests before merge. Integration tests use a test database (not mocks) for data layer.",
        file_path="src/api/auth.ts",
    )
    print(f"  Decision stored: {'✓' if ok else '✗'}")
    print()

    print_banner("Session 1 complete. Run session2 to see cross-session recall!")


def session2() -> None:
    """Simulate a /grill-with-docs skill that benefits from past context."""
    print_banner("SESSION 2: /grill-with-docs skill — Documenting the API")

    mem = SkillMemory()

    # Pre-skill — this time Memanto should return context from session 1
    print_banner("Step 1: Pre-skill query (memories from session 1!)")
    ctx = mem.on_skill_start(
        skill_name="/grill-with-docs",
        file_path="src/api/auth.ts",
        task_description="Write API documentation for authentication endpoints",
    )
    print_context(ctx)

    # The developer can now see their past decisions without re-explaining
    print("  The documentation skill now knows:")
    print("  • Vitest + AAA pattern is the standard")
    print("  • MSW is used for HTTP mocking")
    print("  • Integration tests require a test database")
    print("  • No manual context-shoving needed!")
    print()

    # Store new learnings from this skill
    print_banner("Step 2: Storing /grill-with-docs learnings")
    ok = mem.on_skill_complete(
        skill_name="/grill-with-docs",
        summary="Documentation uses OpenAPI 3.1 spec. All endpoints documented with request/response examples. Error responses follow RFC 7807 (Problem Details).",
        file_path="src/api/auth.ts",
    )
    print(f"  Memory stored: {'✓' if ok else '✗'}")

    print_banner("Demo complete! Zero repeated instructions. 🎉")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("session1", "session2"):
        print(f"Usage: {sys.argv[0]} <session1|session2>")
        return 1

    if sys.argv[1] == "session1":
        session1()
    else:
        session2()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

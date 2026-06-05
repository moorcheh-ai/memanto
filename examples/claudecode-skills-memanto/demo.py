#!/usr/bin/env python3
"""
Demo: Cross-Skill Memory with Memanto + Claude Code Skills
===========================================================

This demo shows how Memanto bridges the context gap between different
Claude Code skill executions. The developer makes a design decision in
one skill session, and that decision automatically propagates to
subsequent skill sessions.

No repeated instructions. No context copy-paste. Zero friction.

Run:
    python demo.py
"""

from __future__ import annotations

import os
from datetime import datetime

from skill_memory import SkillContext, SkillMemory


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def demo_offline() -> None:
    """Demonstration that works WITHOUT a Moorcheh API key using in-memory fallback."""
    mem = SkillMemory()

    # We skip setup() since no API key is available.
    # In-memory fallback is used instead.
    mem._enabled = True  # Override for demo purpose

    print_header("SESSION 1: Architecture Brainstorming with /architect skill")

    # Skill runs, developer makes a decision
    ctx1 = SkillContext(
        skill_name="architect",
        skill_args="design user auth system",
        file_paths=["src/auth/login.py", "src/auth/middleware.py"],
    )

    mem.pre_execute("architect", file_paths=ctx1.file_paths)

    # Developer: "Let's use JWT with refresh token rotation"
    mem.post_execute(
        ctx1,
        summary="Designed JWT auth with refresh token rotation. "
                "Access tokens: 15min TTL. Refresh tokens: 7 days. "
                "Store refresh tokens in Redis with blacklisting support.",
        key_decisions=[
            "Authentication: JWT with refresh token rotation",
            "Token storage: Redis with blacklisted token set",
            "Access token TTL: 15 minutes, Refresh: 7 days",
        ],
        code_patterns=[
            "Use fastapi.security for JWT validation",
            "All auth middleware goes in src/auth/middleware.py",
            "Test with pytest + httpx AsyncClient for async endpoints",
        ],
    )

    print_header("SESSION 2: Writing tests with /tdd skill")

    ctx2 = SkillContext(
        skill_name="tdd",
        skill_args="test auth endpoints",
        file_paths=["tests/test_auth.py", "src/auth/login.py"],
    )

    injected = mem.pre_execute("tdd", file_paths=ctx2.file_paths)
    if injected["injected_context"]:
        print(">>> INJECTED CONTEXT:")
        print(injected["injected_context"])

    # The TDD skill now knows about the auth architecture without re-explanation
    mem.post_execute(
        ctx2,
        summary="Wrote 8 test cases covering JWT creation, validation, "
                "expiry, and refresh rotation. All passing.",
        key_decisions=[
            "Test fixture: auto-create test user with factory_boy before each test",
        ],
        code_patterns=[
            "Use pytest.mark.asyncio for async tests",
            "Mock Redis with fakeredis for CI compatibility",
        ],
    )

    print_header("SESSION 3: Code review with /grill-with-docs skill")

    ctx3 = SkillContext(
        skill_name="grill-with-docs",
        skill_args="review PR #42",
        file_paths=["src/auth/", "tests/test_auth.py"],
    )

    injected3 = mem.pre_execute("grill-with-docs", file_paths=ctx3.file_paths)
    if injected3["injected_context"]:
        print(">>> INJECTED CONTEXT:")
        print(injected3["injected_context"])

    # Reviewer knows the full context: architecture decisions, test patterns, conventions
    mem.post_execute(
        ctx3,
        summary="Reviewed auth PR. Found 2 issues: missing rate limiting on login "
                "endpoint, and refresh token not invalidated on password change. "
                "Approved with minor changes.",
        key_decisions=[
            "Added rate limiting: 5 attempts per minute per IP on /login",
            "Refresh tokens must be invalidated on password change (security)",
        ],
    )

    # --- Final recap ---
    print_header("CROSS-SKILL KNOWLEDGE SUMMARY")
    context = mem.get_cross_skill_context("architect")
    print(context)
    print(f"\nTotal skill executions tracked: {len(mem._skill_history)}")

    print_header("THE VALUE")
    print("""
Without Memanto:
  - Session 2: "What auth pattern did we decide? Let me check Slack..." (3 min lost)
  - Session 3: "What test fixtures are we using? Is Redis mocked?" (2 min lost)
  - Each session starts from zero context.

With Memanto:
  - Session 2: Auth architecture automatically injected from Session 1.
  - Session 3: Full context: auth + test patterns + conventions, zero re-asking.
  - Developer stays in flow state. No context switching.

Bottom line: Zero repeated instructions across all skill sessions.
""")


def demo_with_memanto() -> None:
    """Full demonstration WITH a real Moorcheh API key."""
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        print("Set MOORCHEH_API_KEY to run the full demo.")
        print("Get a free key at: https://moorcheh.ai")
        print("\nRunning offline demo instead...\n")
        demo_offline()
        return

    mem = SkillMemory()
    developer_id = os.environ.get("DEVELOPER_ID", "demo-user")

    if not mem.setup(developer_id=developer_id, api_key=api_key):
        print("Failed to initialize Memanto. Running offline demo.")
        demo_offline()
        return

    # Full online demo (same flow as offline, but backed by real Memanto storage)
    ctx = SkillContext(
        skill_name="architect",
        skill_args="design caching layer",
        file_paths=["src/cache/redis_client.py"],
    )

    mem.pre_execute("architect", file_paths=ctx.file_paths)
    mem.post_execute(
        ctx,
        summary="Designed Redis caching with write-through pattern. "
                "Cache keys: {entity_type}:{id}:{version}. TTL: 5min default.",
        key_decisions=[
            "Caching: Redis write-through pattern",
            "Cache key format: {entity_type}:{id}:{version}",
            "Default TTL: 5 minutes, configurable per entity",
        ],
    )

    # Query memories from a different skill
    memories = mem.recall_recent("caching OR redis")
    print(f"\nRecalled {len(memories)} memories about caching:")
    for m in memories:
        print(f"  - [{m.get('type')}] {m.get('title')}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Memanto + Claude Code Skills: Cross-Skill Memory Demo")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    demo_with_memanto()

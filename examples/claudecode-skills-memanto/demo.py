"""
demo.py
=======
A runnable demonstration of the SkillMemoryBridge showing how Memanto
acts as a persistent memory layer across multiple developer skill executions.

Run this script to see the bridge in action:
    python demo.py

No API key required — runs in LOCAL PREVIEW mode by default.
Set MOORCHEH_API_KEY to use the live Memanto API.
"""

import os
import time
from skill_memory_bridge import SkillMemoryBridge

# Force local preview for this demo (remove to use live API)
os.environ.setdefault("LOCAL_PREVIEW", "true")

DEMO_STORE = ".demo_memories.jsonl"

def separator(title: str = "") -> None:
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print(f"\n{'─' * width}")

def main() -> None:
    print("=" * 60)
    print("  Memanto + Developer Skills Memory Bridge — Demo")
    print("=" * 60)

    # Clean up any previous demo run
    import pathlib
    pathlib.Path(DEMO_STORE).unlink(missing_ok=True)

    bridge = SkillMemoryBridge(local_store_path=DEMO_STORE, verbose=True)

    # -----------------------------------------------------------------------
    # SESSION 1: Developer runs /tdd on the auth service
    # -----------------------------------------------------------------------
    separator("SESSION 1: /tdd — Auth Service Rate Limiting")

    # Before: query for relevant context (empty on first run)
    ctx = bridge.before_skill("tdd", "Add rate limiting to the auth service")
    if ctx:
        print(f"\n📋 Injected context:\n{ctx}")
    else:
        print("\n📋 No prior context — starting fresh.")

    # Simulate skill execution
    print("\n⚙️  [/tdd executing...] Writing tests for token bucket rate limiter...")
    time.sleep(0.5)

    # After: store what was learned
    bridge.after_skill(
        "tdd",
        "Implemented token bucket rate limiter in auth/rate_limit.py. "
        "Used Redis for distributed state. Tests in tests/test_rate_limit.py. "
        "Key decision: 100 req/min per user, burst of 20.",
        tags=["tdd", "auth", "rate-limiting", "redis"],
    )

    # -----------------------------------------------------------------------
    # SESSION 2: Developer runs /grill-with-docs on the same auth module
    # -----------------------------------------------------------------------
    separator("SESSION 2: /grill-with-docs — Auth Module Documentation")

    ctx = bridge.before_skill("grill-with-docs", "Document the auth service rate limiting module")
    if ctx:
        print(f"\n📋 Injected context:\n{ctx}")

    print("\n⚙️  [/grill-with-docs executing...] Generating docs for auth/rate_limit.py...")
    time.sleep(0.5)

    bridge.after_skill(
        "grill-with-docs",
        "Documented auth/rate_limit.py. Added docstrings and a RATE_LIMITING.md guide. "
        "Noted that Redis connection string must be set via REDIS_URL env var.",
        tags=["grill-with-docs", "auth", "documentation", "redis"],
    )

    # -----------------------------------------------------------------------
    # SESSION 3: Developer runs /handoff — memory from both prior sessions injected
    # -----------------------------------------------------------------------
    separator("SESSION 3: /handoff — Prepare Handoff for Auth Changes")

    ctx = bridge.before_skill("handoff", "Prepare handoff notes for auth service changes")
    if ctx:
        print(f"\n📋 Injected context (from prior sessions):\n{ctx}")
    else:
        print("\n📋 No context found.")

    print("\n⚙️  [/handoff executing...] Generating handoff document...")
    time.sleep(0.5)

    bridge.after_skill(
        "handoff",
        "Handoff document created: HANDOFF_AUTH_2026-05-20.md. "
        "Covers rate limiter implementation, Redis dependency, and documentation location.",
        tags=["handoff", "auth"],
    )

    # -----------------------------------------------------------------------
    # SESSION 4: New session — /tdd on a different feature, but auth context surfaces
    # -----------------------------------------------------------------------
    separator("SESSION 4: /tdd — Payment Service (Redis also used here)")

    ctx = bridge.before_skill("tdd", "Add idempotency keys to the payment service using Redis")
    if ctx:
        print(f"\n📋 Injected context (Redis memory surfaces from auth work):\n{ctx}")

    print("\n⚙️  [/tdd executing...] Writing tests for payment idempotency...")
    time.sleep(0.5)

    bridge.after_skill(
        "tdd",
        "Implemented idempotency keys in payments/idempotency.py using Redis. "
        "Reused the same Redis connection pattern from auth/rate_limit.py (REDIS_URL env var).",
        tags=["tdd", "payments", "idempotency", "redis"],
    )

    # -----------------------------------------------------------------------
    # Final: Show the full Engineering Profile
    # -----------------------------------------------------------------------
    separator("Engineering Profile — All Stored Memories")

    profile = bridge.get_engineering_profile()
    for i, mem in enumerate(profile, 1):
        print(f"\n{i}. [{mem['skill']}] {mem['content'][:100]}...")
        print(f"   Tags: {mem['tags']} | Time: {mem['timestamp'][:19]}")

    separator()
    print("\n✅ Demo complete!")
    print(f"   {len(profile)} memories stored in: {DEMO_STORE}")
    print("\n   Key insight: In SESSION 4, the Redis knowledge from SESSION 1")
    print("   was automatically surfaced — no repeated instructions needed.")
    print("\n   This is the Engineering Profile in action: zero repeated context,")
    print("   consistent architectural decisions across all skill executions.")

    # Clean up demo store
    import pathlib
    pathlib.Path(DEMO_STORE).unlink(missing_ok=True)


if __name__ == "__main__":
    main()

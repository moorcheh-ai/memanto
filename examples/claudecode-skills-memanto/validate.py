"""
validate.py
===========
Automated validation script for the SkillMemoryBridge.
Verifies that the bridge correctly stores and retrieves memories
in both LOCAL PREVIEW and (optionally) LIVE MEMANTO modes.

Run:
    python validate.py              # local preview validation
    MOORCHEH_API_KEY=... python validate.py  # live API validation
"""

import os
import pathlib
import sys
import uuid

# Force local for automated validation unless explicitly set to live
if not os.environ.get("MOORCHEH_API_KEY"):
    os.environ["LOCAL_PREVIEW"] = "true"

# When running against live Memanto, isolate all writes into a dedicated
# test namespace so the suite never contaminates the user's real
# Engineering Profile data. Each run uses a unique suffix so concurrent or
# repeated runs cannot interfere with each other either.
if os.environ.get("MOORCHEH_API_KEY") and os.environ.get("LOCAL_PREVIEW", "").lower() != "true":
    # Allow the user to override with an explicit MEMANTO_TEST_NAMESPACE
    # but otherwise always pick a fresh, scoped namespace.
    if not os.environ.get("MEMANTO_TEST_NAMESPACE"):
        os.environ["MEMANTO_TEST_NAMESPACE"] = (
            f"validate-test-{uuid.uuid4().hex[:8]}"
        )
    # Force the bridge to use the test namespace regardless of any
    # MEMANTO_NAMESPACE the user may have configured for normal use.
    os.environ["MEMANTO_NAMESPACE"] = os.environ["MEMANTO_TEST_NAMESPACE"]

from skill_memory_bridge import SkillMemoryBridge

PASS = "✅ PASS"
FAIL = "❌ FAIL"
TEST_STORE = ".validate_test.jsonl"
TEST_NAMESPACE = os.environ.get("MEMANTO_TEST_NAMESPACE")

def run_test(name: str, fn) -> bool:
    try:
        fn()
        print(f"  {PASS}: {name}")
        return True
    except AssertionError as e:
        print(f"  {FAIL}: {name} — {e}")
        return False
    except Exception as e:
        print(f"  {FAIL}: {name} — Unexpected error: {e}")
        return False

def cleanup():
    pathlib.Path(TEST_STORE).unlink(missing_ok=True)

def test_bridge_initializes():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    assert bridge.mode in ("local", "live"), f"Unexpected mode: {bridge.mode}"
    cleanup()

def test_after_skill_stores_memory():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    bridge.after_skill("tdd", "Used pytest fixtures for database tests", tags=["tdd", "testing"])
    profile = bridge.get_engineering_profile()
    assert len(profile) == 1, f"Expected 1 memory, got {len(profile)}"
    assert "pytest" in profile[0]["content"]
    cleanup()

def test_before_skill_returns_empty_on_no_memories():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    ctx = bridge.before_skill("tdd", "Add rate limiting")
    assert ctx == "", f"Expected empty string, got: {ctx!r}"
    cleanup()

def test_before_skill_returns_relevant_memories():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    bridge.after_skill("tdd", "Used Redis for rate limiting in auth service", tags=["tdd", "redis"])
    bridge.after_skill("handoff", "Wrote handoff for payment service", tags=["handoff", "payments"])
    ctx = bridge.before_skill("tdd", "Add Redis-based caching to the API")
    assert "Redis" in ctx, f"Expected Redis memory to be surfaced, got: {ctx}"
    cleanup()

def test_cross_skill_memory_retrieval():
    """Memories from one skill should surface when relevant to another skill."""
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    bridge.after_skill("tdd", "All database tests use a shared PostgreSQL fixture", tags=["tdd", "postgresql", "database"])
    # A different skill asking about databases should find this
    ctx = bridge.before_skill("grill-with-docs", "Document the database connection pooling setup")
    assert "PostgreSQL" in ctx or "database" in ctx.lower(), \
        f"Expected cross-skill memory retrieval, got: {ctx}"
    cleanup()

def test_multiple_memories_stored_and_retrieved():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    for i in range(5):
        bridge.after_skill("tdd", f"Test memory {i}: topic_{i}", tags=["tdd", f"topic_{i}"])
    profile = bridge.get_engineering_profile()
    assert len(profile) == 5, f"Expected 5 memories, got {len(profile)}"
    cleanup()

def test_tags_improve_retrieval():
    cleanup()
    bridge = SkillMemoryBridge(local_store_path=TEST_STORE, verbose=False)
    bridge.after_skill("tdd", "Unrelated content about cooking recipes", tags=["tdd", "cooking"])
    bridge.after_skill("tdd", "Auth service uses JWT tokens with 1h expiry", tags=["tdd", "auth", "jwt"])
    ctx = bridge.before_skill("tdd", "Add JWT refresh token support to auth")
    assert "JWT" in ctx, f"Expected JWT memory to be surfaced, got: {ctx}"
    cleanup()


def main():
    print("=" * 55)
    print("  SkillMemoryBridge — Validation Suite")
    print("=" * 55)

    mode = "LOCAL PREVIEW" if os.environ.get("LOCAL_PREVIEW") == "true" else "LIVE MEMANTO"
    print(f"\nMode: {mode}")
    if TEST_NAMESPACE:
        print(f"Live test namespace (isolated): {TEST_NAMESPACE}")
    print()

    tests = [
        ("Bridge initializes correctly", test_bridge_initializes),
        ("after_skill() stores memory", test_after_skill_stores_memory),
        ("before_skill() returns empty when no memories", test_before_skill_returns_empty_on_no_memories),
        ("before_skill() returns relevant memories", test_before_skill_returns_relevant_memories),
        ("Cross-skill memory retrieval works", test_cross_skill_memory_retrieval),
        ("Multiple memories stored and retrieved", test_multiple_memories_stored_and_retrieved),
        ("Tags improve retrieval precision", test_tags_improve_retrieval),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        if run_test(name, fn):
            passed += 1
        else:
            failed += 1

    print(f"\n{'─' * 55}")
    print(f"Results: {passed}/{len(tests)} passed")

    if failed == 0:
        print("✅ All tests passed! The bridge is working correctly.")
        sys.exit(0)
    else:
        print(f"❌ {failed} test(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()

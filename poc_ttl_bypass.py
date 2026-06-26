"""
PoC: TTL Bypass via Type Confusion — Fixed Verification
Issue: #770 - Memanto Bug & Exploit Challenge

This script calls _filter_expired_memories directly on MemoryReadService
to prove that AFTER the fix, memories with expires_at set to integer,
string (past), or invalid types are ALL filtered out.

Run: python poc_ttl_bypass.py
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from memanto.app.services.memory_read_service import MemoryReadService


def make_memory(expires_at_value, memory_id="test-001"):
    """Create a mock memory dict with the given expires_at value."""
    return {
        "id": memory_id,
        "title": "Test memory",
        "content": "This memory has a manipulated expires_at",
        "type": "fact",
        "confidence": 0.9,
        "status": "active",
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at_value,
    }


def main():
    print("=" * 60)
    print("PoC: TTL Bypass via Type Confusion — Fixed Verification")
    print("=" * 60)

    now = datetime.now(timezone.utc)

    # Build test memories with various expires_at types
    past_int = int((now - timedelta(hours=1)).timestamp())       # integer, past
    future_int = int((now + timedelta(hours=1)).timestamp())      # integer, future (should be kept)
    past_str = (now - timedelta(hours=1)).isoformat()             # string, past
    future_str = (now + timedelta(hours=1)).isoformat()           # string, future (should be kept)
    invalid_list = [2026, 1, 1]                                   # list, invalid type
    none_value = None                                             # None, no expiry (should be kept)
    falsy_int = 0                                                 # integer 0, falsy (should be filtered)
    falsy_str = ""                                                # empty string, falsy (should be filtered)

    test_memories = [
        make_memory(past_int, "expired-int"),
        make_memory(future_int, "future-int"),
        make_memory(past_str, "expired-str"),
        make_memory(future_str, "future-str"),
        make_memory(invalid_list, "invalid-list"),
        make_memory(none_value, "no-expiry"),
        make_memory(falsy_int, "falsy-int-zero"),
        make_memory(falsy_str, "falsy-empty-str"),
    ]

    print("\nInput memories:")
    for m in test_memories:
        print(f"  - {m['id']}: expires_at={m['expires_at']!r} (type={type(m['expires_at']).__name__})")

    # Create MemoryReadService with a mock client — _filter_expired_memories
    # does not use self.client, so a MagicMock is sufficient.
    service = MemoryReadService(moorcheh_client=MagicMock())

    # Call _filter_expired_memories directly
    try:
        filtered = service._filter_expired_memories(test_memories)
    except (ValueError, AttributeError):
        filtered = []

    print(f"\nAfter _filter_expired_memories: {len(filtered)} memories kept")
    for m in filtered:
        print(f"  - {m['id']}: expires_at={m['expires_at']!r} (type={type(m['expires_at']).__name__})")

    # Assertions
    kept_ids = {m["id"] for m in filtered}
    expected_kept = {"future-int", "future-str", "no-expiry"}
    expected_filtered = {"expired-int", "expired-str", "invalid-list", "falsy-int-zero", "falsy-empty-str"}

    print("\n" + "-" * 60)
    print("Verification:")
    all_pass = True

    for mid in expected_kept:
        status = "PASS" if mid in kept_ids else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] {mid} should be KEPT")

    for mid in expected_filtered:
        status = "PASS" if mid not in kept_ids else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] {mid} should be FILTERED OUT")

    print("\n" + "=" * 60)
    if all_pass:
        print("ALL CHECKS PASSED — TTL bypass is fixed!")
        print("""
After the fix:
  - Integer timestamps (past/future) are properly handled
  - String timestamps (past/future) are properly handled
  - Invalid types (list) are filtered out to prevent bypass
  - Falsy values (0, empty string) are filtered out, not treated as "no expiry"
  - None/missing expires_at is kept (no expiry = permanent)
""")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED — TTL bypass may still exist!")
        sys.exit(1)


if __name__ == "__main__":
    main()

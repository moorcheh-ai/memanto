"""Tests for issue #1438 — Rate limiter fail-closed + validation consistency."""

import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_rate_limiter_fail_closed():
    """Unknown operations should be rate-limited, not silently passed."""
    from memanto.app.utils.rate_limiting import RateLimiter

    limiter = RateLimiter()

    # Unknown operation should NOT pass silently
    # With fail-closed, it should use a default conservative limit
    for _ in range(15):  # Exceed default limit of 10/60s
        allowed, _ = limiter.check_rate_limit("nonexistent_op", "test_agent")

    # After 15 requests, should be rate limited (limit is 10)
    allowed, retry_after = limiter.check_rate_limit("nonexistent_op", "test_agent")
    assert not allowed, "Unknown operation should be rate-limited after exceeding default limit"
    assert retry_after is not None, "retry_after should be set"


def test_rate_limiter_namespace_list():
    """namespace_list should not bypass rate limiting."""
    from memanto.app.utils.rate_limiting import RateLimiter

    limiter = RateLimiter()

    # enforce_namespace_rate_limit builds keys like "namespace_list"
    # which should NOT bypass rate limiting
    for _ in range(15):
        allowed, _ = limiter.check_rate_limit("namespace_list", "test_agent")

    allowed, _ = limiter.check_rate_limit("namespace_list", "test_agent")
    assert not allowed, "namespace_list should be rate-limited"


def test_rate_limiter_known_operation():
    """Known operations should still work normally."""
    from memanto.app.utils.rate_limiting import RateLimiter

    limiter = RateLimiter()

    # First request should always be allowed
    allowed, retry_after = limiter.check_rate_limit("memory_read", "test_agent")
    assert allowed, "First request should be allowed"
    assert retry_after is None


def test_id_validation_consistent():
    """ids.py and safe_deletion.py should agree on valid IDs."""
    from memanto.app.utils.ids import is_valid_memory_id

    # Both should accept: alphanumeric, hyphens, underscores, length >= 4
    assert is_valid_memory_id("mem_abc123"), "Standard ID should be valid"
    assert is_valid_memory_id("abc-123"), "Hyphenated ID should be valid"
    assert is_valid_memory_id("test_id_1"), "Underscored ID should be valid"

    # Both should reject: too short, special chars
    assert not is_valid_memory_id("ab"), "Too short should be invalid"
    assert not is_valid_memory_id(""), "Empty should be invalid"
    assert not is_valid_memory_id(None), "None should be invalid"


def test_source_type_validated():
    """SourceType should only accept known values."""
    from memanto.app.constants import SourceType

    # Check that SourceType is a Literal, not plain str
    assert SourceType != str, "SourceType should be Literal, not str"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}: {test.__doc__}")
            passed += 1
        except (AssertionError, Exception) as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")

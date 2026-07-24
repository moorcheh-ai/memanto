"""Tests for rate limiter fail-open fix, ID validation consistency, and SourceType validation.

Covers:
- Rate limiter denies unknown operations (fail-closed)
- Rate limiter still allows known operations
- Rate limiter enforces limits correctly
- ID validation is consistent between ids.py and safe_deletion.py
- SourceType validation helper works correctly
"""

import time

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Rate Limiter Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRateLimiterFailClosed:
    """Verify fail-closed behavior for unknown operations."""

    def test_unknown_operation_denied(self):
        """Unknown operations must be denied (fail-closed)."""
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        allowed, retry_after = limiter.check_rate_limit("nonexistent_op", "agent1")
        assert allowed is False
        assert retry_after is not None

    def test_namespace_list_bypass_blocked(self):
        """The specific bypass vector from #1438 must be blocked.

        enforce_namespace_rate_limit('list', agent) builds key 'namespace_list'
        which is not in the limits dict — previously allowed, now denied.
        """
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        # namespace_list is NOT a configured operation
        allowed, _ = limiter.check_rate_limit("namespace_list", "test_agent")
        assert allowed is False

    def test_arbitrary_string_denied(self):
        """Any arbitrary operation string must be denied."""
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        for op in ["", "drop_table", "admin_override", "x" * 1000]:
            allowed, _ = limiter.check_rate_limit(op, "agent1")
            assert allowed is False, f"Operation '{op[:20]}' should be denied"

    def test_known_operations_still_allowed(self):
        """All configured operations must still work."""
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        known_ops = [
            "memory_write", "memory_read", "memory_answer",
            "memory_delete", "namespace_create", "namespace_delete", "health",
        ]
        for op in known_ops:
            allowed, retry_after = limiter.check_rate_limit(op, "agent1")
            assert allowed is True, f"Known operation '{op}' should be allowed"
            assert retry_after is None

    def test_rate_limit_enforced_after_exhaustion(self):
        """Rate limit kicks in after exceeding request count."""
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        # health allows 300/min — exhaust it
        for i in range(300):
            allowed, _ = limiter.check_rate_limit("health", "flood_agent")
            assert allowed is True

        # 301st should be denied
        allowed, retry_after = limiter.check_rate_limit("health", "flood_agent")
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    def test_rate_limit_per_agent_isolation(self):
        """Rate limits are per-agent — one agent's usage doesn't affect another."""
        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        # Use up agent1's write limit (60/min)
        for i in range(60):
            limiter.check_rate_limit("memory_write", "agent1")

        # agent2 should still be allowed
        allowed, _ = limiter.check_rate_limit("memory_write", "agent2")
        assert allowed is True

    def test_enforce_rate_limit_raises_on_unknown(self):
        """enforce_rate_limit must raise HTTPException for unknown ops."""
        from fastapi import HTTPException

        from memanto.app.utils.rate_limiting import RateLimiter

        limiter = RateLimiter()
        with pytest.raises(HTTPException) as exc_info:
            limiter.enforce_rate_limit("unknown_op", "agent1")
        assert exc_info.value.status_code == 429


# ══════════════════════════════════════════════════════════════════════════════
# ID Validation Consistency Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestIDValidationConsistency:
    """Verify ids.py and safe_deletion.py agree on what's a valid memory ID."""

    def test_generated_id_valid_in_both(self):
        """IDs from generate_memory_id must pass both validators."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        from memanto.app.utils.ids import generate_memory_id, is_valid_memory_id

        for _ in range(10):
            mid = generate_memory_id()
            assert is_valid_memory_id(mid), f"ids.py rejected generated ID: {mid}"
            assert SafeDeletion._is_valid_memory_id(mid), f"safe_deletion rejected generated ID: {mid}"

    def test_no_underscore_rejected_by_both(self):
        """IDs without underscore must fail both validators."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        from memanto.app.utils.ids import is_valid_memory_id

        invalid_ids = ["abc-123", "abcdef", "12345678"]
        for mid in invalid_ids:
            assert not is_valid_memory_id(mid), f"ids.py accepted '{mid}' without underscore"
            assert not SafeDeletion._is_valid_memory_id(mid), f"safe_deletion accepted '{mid}' without underscore"

    def test_short_ids_rejected_by_both(self):
        """IDs with length <= 4 must fail both validators."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        from memanto.app.utils.ids import is_valid_memory_id

        short_ids = ["", "a", "ab", "a_b", "ab_c"]
        for mid in short_ids:
            assert not is_valid_memory_id(mid), f"ids.py accepted short ID: '{mid}'"
            assert not SafeDeletion._is_valid_memory_id(mid), f"safe_deletion accepted short ID: '{mid}'"

    def test_valid_format_accepted_by_both(self):
        """Standard prefix_hash format passes both."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        from memanto.app.utils.ids import is_valid_memory_id

        valid_ids = ["mem_abc123def", "event_12345", "fact_abcdefgh"]
        for mid in valid_ids:
            assert is_valid_memory_id(mid), f"ids.py rejected valid ID: '{mid}'"
            assert SafeDeletion._is_valid_memory_id(mid), f"safe_deletion rejected valid ID: '{mid}'"

    def test_special_chars_handled_consistently(self):
        """IDs with only hyphens (no underscore) rejected by both."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        from memanto.app.utils.ids import is_valid_memory_id

        # Has hyphen but no underscore
        mid = "abc-123-def"
        assert not is_valid_memory_id(mid)
        assert not SafeDeletion._is_valid_memory_id(mid)


# ══════════════════════════════════════════════════════════════════════════════
# SourceType Validation Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestSourceTypeValidation:
    """Verify SourceType has known values and validation."""

    def test_known_sources_recognized(self):
        """Standard source types are recognized."""
        from memanto.app.constants import is_known_source_type

        for source in ["user", "agent", "tool", "system"]:
            assert is_known_source_type(source), f"'{source}' should be known"

    def test_agent_prefix_recognized(self):
        """Custom agent names with agent_ prefix are valid."""
        from memanto.app.constants import is_known_source_type

        assert is_known_source_type("agent_hermes")
        assert is_known_source_type("agent_memory_bot")

    def test_arbitrary_strings_flagged(self):
        """Arbitrary strings are not recognized as known sources."""
        from memanto.app.constants import is_known_source_type

        for source in ["", "random", "DROP TABLE", "../../etc/passwd"]:
            assert not is_known_source_type(source), f"'{source}' should not be known"

    def test_known_source_types_frozenset_exists(self):
        """KNOWN_SOURCE_TYPES constant is available for external use."""
        from memanto.app.constants import KNOWN_SOURCE_TYPES

        assert isinstance(KNOWN_SOURCE_TYPES, frozenset)
        assert len(KNOWN_SOURCE_TYPES) >= 4
        assert "user" in KNOWN_SOURCE_TYPES

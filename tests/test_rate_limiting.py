"""Tests for memanto.app.utils.rate_limiting (Finding 1 in #1438).

Before the fix, `check_rate_limit` silently returned `(True, None)` for
unknown operations, which let `enforce_namespace_rate_limit(op, agent_id)`
bypass rate limiting whenever the operation wasn't registered. The fix
makes the limiter fail-closed.
"""

import pytest

from memanto.app.utils.rate_limiting import RateLimiter, enforce_namespace_rate_limit


class TestRateLimiterFailClosed:
    """Unknown operations must NOT silently pass."""

    def setup_method(self):
        self.limiter = RateLimiter()

    def test_unknown_operation_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            self.limiter.check_rate_limit("nonexistent_op", "agent-1")
        assert "nonexistent_op" in str(exc_info.value)
        # Allowed operations are listed in the error to aid debugging.
        assert "memory_write" in str(exc_info.value)

    def test_namespace_prefix_bypass_no_longer_works(self):
        """`enforce_namespace_rate_limit(op, agent_id)` builds keys like
        `namespace_<op>`. Before the fix, any operation unknown to the
        limiter (e.g. `list`) bypassed rate limiting entirely. After the
        fix it raises."""
        with pytest.raises(ValueError):
            enforce_namespace_rate_limit("list", "agent-1")

    def test_known_operation_still_passes_under_limit(self):
        # Sanity check: registered operations are not broken by the fix.
        allowed, retry = self.limiter.check_rate_limit("memory_write", "agent-1")
        assert allowed is True
        assert retry is None

    def test_known_operation_still_blocks_over_limit(self):
        # Saturate the bucket then assert the limiter blocks instead of raising.
        for _ in range(self.limiter.limits["memory_write"].requests):
            allowed, _ = self.limiter.check_rate_limit("memory_write", "agent-2")
            assert allowed is True
        allowed, retry = self.limiter.check_rate_limit("memory_write", "agent-2")
        assert allowed is False
        assert retry is not None
        assert retry >= 1

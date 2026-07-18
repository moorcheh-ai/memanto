"""
Regression tests for fail-closed rate limiting (issue #1438).

Previously, `check_rate_limit` returned `True` for any operation not present
in `self.limits` (fail-open), letting unknown/typo'd operations bypass all
rate limiting. Now unknown operations fall back to a conservative default
limit instead of being silently allowed.
"""
import time

from memanto.app.utils.rate_limiting import RateLimiter


def test_unknown_operation_is_rate_limited_fail_closed():
    """An unconfigured operation must be limited (not silently allowed).

    Fail-closed means unknown ops are capped by the conservative default
    (30/60s) instead of being unlimited. After exhausting the default
    window the request is denied.
    """
    rl = RateLimiter()
    allowed_count = 0
    for _ in range(35):
        allowed, _ = rl.check_rate_limit("totally_unknown_op", "agent-x")
        if allowed:
            allowed_count += 1
    assert allowed_count == 30


def test_unknown_operation_returns_retry_after_when_exhausted():
    rl = RateLimiter()
    for _ in range(30):
        rl.check_rate_limit("totally_unknown_op", "agent-y")
    allowed, retry_after = rl.check_rate_limit("totally_unknown_op", "agent-y")
    assert allowed is False
    assert isinstance(retry_after, int) and retry_after > 0


def test_known_operation_still_works():
    rl = RateLimiter()
    # health allows 300/60s, so a single call is allowed
    allowed, retry_after = rl.check_rate_limit("health", "agent-z")
    assert allowed is True
    assert retry_after is None


def test_known_operation_enforces_limit():
    rl = RateLimiter()
    op = "memory_answer"  # 30 requests / 60s
    allowed_count = 0
    for _ in range(35):
        allowed, _ = rl.check_rate_limit(op, "agent-limit")
        if allowed:
            allowed_count += 1
    assert allowed_count == 30


def test_unknown_operation_enforces_default_limit():
    """Unknown ops use the conservative default (30/60s), not unlimited."""
    rl = RateLimiter()
    allowed_count = 0
    for _ in range(35):
        allowed, _ = rl.check_rate_limit("weird_op", "agent-def")
        if allowed:
            allowed_count += 1
    assert allowed_count == 30

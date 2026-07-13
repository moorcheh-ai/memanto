import pytest
from fastapi import HTTPException

from memanto.app.legacy.safe_deletion import SafeDeletion
from memanto.app.utils.ids import is_valid_memory_id
from memanto.app.utils.rate_limiting import RateLimiter


def test_unknown_rate_limit_operation_fails_closed():
    limiter = RateLimiter()

    with pytest.raises(ValueError, match="Unknown rate-limited operation"):
        limiter.check_rate_limit("namespace_list", "agent-1")


def test_enforce_rate_limit_reports_misconfiguration_for_unknown_operation():
    limiter = RateLimiter()

    with pytest.raises(HTTPException) as exc_info:
        limiter.enforce_rate_limit("namespace_list", "agent-1")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == "rate_limit_misconfigured"


def test_known_rate_limit_operation_still_allows_first_request():
    limiter = RateLimiter()

    allowed, retry_after = limiter.check_rate_limit("memory_read", "agent-1")

    assert allowed is True
    assert retry_after is None


@pytest.mark.parametrize(
    "memory_id",
    [
        "mem_123456789abc",
        "abc-123",
        "abcd",
    ],
)
def test_safe_deletion_uses_canonical_memory_id_validator(memory_id):
    assert SafeDeletion._is_valid_memory_id(memory_id) is is_valid_memory_id(memory_id)

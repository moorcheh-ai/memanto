"""Regression tests for trailing-newline bypass in ID validation.

Bug: re.match(r"^...$", value) returns True for "value\\n" because $ matches
before a final \\n even without re.MULTILINE. This allows IDs with trailing
newlines to pass validation, potentially causing:
- Cache key pollution
- Log injection
- File path issues
- HTTP header injection

Fix: use re.fullmatch() instead of re.match() with $.
"""
import re
import pytest


class TestTrailingNewlineBypass:
    """Verify that ID validation rejects trailing newlines."""

    @pytest.mark.parametrize("key", [
        "valid_id_123\n",           # trailing \n
        "valid_id_123\r\n",         # trailing \r\n (Windows)
    ])
    def test_idempotency_key_rejects_trailing_newline(self, key):
        """Idempotency keys with trailing newlines must be rejected."""
        from memanto.app.legacy.idempotency import IdempotencyHandler
        assert not IdempotencyHandler.validate_idempotency_key(key), \
            f"Idempotency key {repr(key)} should be rejected (trailing newline bypass)"

    @pytest.mark.parametrize("memory_id", [
        "valid_mem_id\n",
        "valid_mem_id\r\n",
    ])
    def test_memory_id_rejects_trailing_newline(self, memory_id):
        """Memory IDs with trailing newlines must be rejected."""
        from memanto.app.legacy.safe_deletion import SafeDeletion
        assert not SafeDeletion._is_valid_memory_id(memory_id), \
            f"Memory ID {repr(memory_id)} should be rejected (trailing newline bypass)"

    def test_valid_ids_still_accepted(self):
        """Normal valid IDs must still pass validation."""
        from memanto.app.legacy.idempotency import IdempotencyHandler
        assert IdempotencyHandler.validate_idempotency_key("valid_key_123")
        assert IdempotencyHandler.validate_idempotency_key("abc-def-123")

    def test_re_match_dollar_bypass_documented(self):
        """Document the re.match $ vulnerability for future reference."""
        # This test documents WHY we use fullmatch instead of match+$
        key = "valid_id\n"
        assert re.match(r"^[a-zA-Z0-9_-]+$", key)  # VULNERABLE: returns True
        assert not re.fullmatch(r"[a-zA-Z0-9_-]+", key)  # FIXED: returns False

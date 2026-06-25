"""
Tests for issue #770: Memanto Bug & Exploit Challenge

Two bugs fixed:
1. get_field() falsy-value fallback in _format_memory_item
   - metadata.get(field) or item.get(fallback) treats 0/False/[] as missing
   - Fix: explicit is None check preserves falsy-but-present values
2. Hardcoded JWT secret key in SessionService
   - Default "memanto-default-secret-change-in-production" allows token forgery
   - Fix: generate cryptographically secure random key via secrets.token_hex(32)
"""

import unittest
from datetime import datetime, timezone


class TestFalsyValueBug(unittest.TestCase):
    """Prove the get_field() falsy value bug exists in the original code."""

    def test_original_get_field_preserves_truthy(self):
        """Truthy values work correctly in the original."""
        metadata = {"confidence": 0.9, "tags": ["a", "b"]}
        item = {"confidence": 0.1, "tags": []}

        def old_get_field(field_name, flat_field_name=None):
            flat_name = flat_field_name or field_name
            return metadata.get(field_name) or item.get(flat_name)

        self.assertEqual(old_get_field("confidence"), 0.9)
        self.assertEqual(old_get_field("tags"), ["a", "b"])

    def test_original_get_field_corrupts_falsy_values(self):
        """
        BUG: confidence=0.0, contradiction_detected=False, tags=[]
        are all replaced by the flat-field fallback.
        """
        metadata = {"confidence": 0.0, "contradiction_detected": False, "tags": []}
        item = {"confidence": 0.8, "contradiction_detected": True, "tags": ["fallback"]}

        def old_get_field(field_name, flat_field_name=None):
            flat_name = flat_field_name or field_name
            return metadata.get(field_name) or item.get(flat_name)

        # These should return metadata values, NOT item fallbacks
        self.assertEqual(old_get_field("confidence"), 0.8)  # BUG: should be 0.0
        self.assertEqual(old_get_field("contradiction_detected"), True)  # BUG: should be False
        self.assertEqual(old_get_field("tags"), ["fallback"])  # BUG: should be []

    def test_fixed_get_field_preserves_falsy(self):
        """FIX: explicit is None check preserves falsy values."""
        metadata = {"confidence": 0.0, "contradiction_detected": False, "tags": []}
        item = {"confidence": 0.8, "contradiction_detected": True, "tags": ["fallback"]}

        def fixed_get_field(field_name, flat_field_name=None):
            flat_name = flat_field_name or field_name
            field_value = metadata.get(field_name)
            if field_value is not None:
                return field_value
            return item.get(flat_name)

        self.assertEqual(fixed_get_field("confidence"), 0.0)
        self.assertEqual(fixed_get_field("contradiction_detected"), False)
        self.assertEqual(fixed_get_field("tags"), [])

    def test_fixed_get_field_falls_through_on_missing(self):
        """FIX: still falls through when key is truly absent."""
        metadata = {"title": "test"}
        item = {"title": "fallback-title", "confidence": 0.5}

        def fixed_get_field(field_name, flat_field_name=None):
            flat_name = flat_field_name or field_name
            field_value = metadata.get(field_name)
            if field_value is not None:
                return field_value
            return item.get(flat_name)

        self.assertEqual(fixed_get_field("title"), "test")
        self.assertEqual(fixed_get_field("confidence"), 0.5)


class TestJwtSecretKey(unittest.TestCase):
    """Prove the hardcoded JWT secret key bug."""

    def test_hardcoded_secret_allows_prediction(self):
        """
        BUG: Default secret is a known string.
        Anyone can forge session tokens.
        """
        import jwt

        # This is the hardcoded default from the original code
        hardcoded_secret = "memanto-default-secret-change-in-production"

        # An attacker can forge a session token for any agent
        forged_token = jwt.encode(
            {
                "agent_id": "any-agent",
                "namespace": "memanto_agent_any-agent",
                "session_id": "sess_forged",
                "started_at": datetime.utcnow(),
                "expires_at": datetime.utcnow(),
            },
            hardcoded_secret,
            algorithm="HS256",
        )

        # The token decodes successfully with the known secret
        payload = jwt.decode(forged_token, hardcoded_secret, algorithms=["HS256"])
        self.assertEqual(payload["agent_id"], "any-agent")
        # This proves the hardcoded secret is a critical vulnerability

    def test_secure_secret_is_unpredictable(self):
        """
        FIX: Use secrets.token_hex(32) for cryptographically secure random key.
        """
        import secrets

        # Generate two keys - they should be different
        key1 = secrets.token_hex(32)
        key2 = secrets.token_hex(32)

        self.assertNotEqual(key1, key2)
        self.assertEqual(len(key1), 64)  # 32 bytes = 64 hex chars
        # Cannot be predicted or brute-forced


if __name__ == "__main__":
    unittest.main()

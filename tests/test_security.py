"""Security tests for Memanto API key validation and input sanitization."""

import os
import pytest


class TestAPIKeyValidation:
    """Tests for API key security validation."""

    def test_valid_api_key_accepted(self):
        """Test that a properly formatted API key is accepted."""
        from memanto.client import MemantoClient
        
        client = MemantoClient(api_key="mch_validkey1234567890123456")
        assert client.api_key == "mch_validkey1234567890123456"

    def test_missing_api_key_raises(self):
        """Test that missing API key raises ValueError."""
        from memanto.client import MemantoClient
        
        # Ensure no env var is set
        old_key = os.environ.pop("MOORCHEH_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="MOORCHEH_API_KEY is required"):
                MemantoClient(api_key="")
        finally:
            if old_key is not None:
                os.environ["MOORCHEH_API_KEY"] = old_key

    def test_newline_injection_blocked(self):
        """Test that newline characters in API key are rejected (CRLF injection)."""
        from memanto.client import MemantoClient
        
        with pytest.raises(ValueError, match="invalid characters"):
            MemantoClient(api_key="mch_valid\nHost: evil.com")

    def test_command_injection_blocked(self):
        """Test that shell metacharacters in API key are rejected."""
        from memanto.client import MemantoClient
        
        with pytest.raises(ValueError, match="invalid characters"):
            MemantoClient(api_key="mch_valid; cat /etc/passwd")

    def test_short_api_key_rejected(self):
        """Test that too-short API keys are rejected."""
        from memanto.client import MemantoClient
        
        with pytest.raises(ValueError, match="at least 16 alphanumeric"):
            MemantoClient(api_key="mch_short")
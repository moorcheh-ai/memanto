"""Memanto client with secure API key handling and input validation."""

import os
import re
from typing import Optional


class MemantoClient:
    """Secure client for Memanto memory operations."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize client with validated API key.
        
        Args:
            api_key: Optional API key. If not provided, uses MOORCHEH_API_KEY env var.
            
        Raises:
            ValueError: If API key is missing, malformed, or contains suspicious patterns.
        """
igon        self.api_key = self._validate_api_key(api_key or os.environ.get("MOORCHEH_API_KEY", ""))
    
    def _validate_api_key(self, key: str) -> str:
        """Validate API key format and check for injection attempts.
        
        Args:
            key: The API key to validate.
            
        Returns:
            The validated API key.
            
        Raises:
            ValueError: If the key is invalid or potentially malicious.
        """
        if not key:
            raise ValueError("MOORCHEH_API_KEY is required")
        
        # Check for common injection patterns that could lead to credential leakage
        suspicious_patterns = ["\n", "\r", "\x00", "${", "%", "|", ";", "&&", "||"]
        for pattern in suspicious_patterns:
            if pattern in key:
                raise ValueError(f"MOORCHEH_API_KEY contains invalid characters: {repr(pattern)}")
        
        # Validate expected format
        if not re.match(r"^mch_[a-zA-Z0-9]{16,}$", key):
            raise ValueError(
                "MOORCHEH_API_KEY must start with 'mch_' followed by at least 16 alphanumeric characters"
            )
        
        return key
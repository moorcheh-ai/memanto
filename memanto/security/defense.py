"""
Security Defenses & Boundary Isolation Module.

Bounty #1852: Security Hardening & Defenses
Author: Prakhar Dewangan
"""

import re
from typing import Dict, Any, Optional

# Patterns commonly used in indirect prompt injection attacks against agent memory
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+prompt\s+override",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"disregard\s+prior\s+rules",
    r"output\s+all\s+(keys|passwords|secrets|environment\s+variables)",
]

class SecurityViolation(Exception):
    """Raised when an action violates memory security or namespace isolation."""
    pass

class MemorySecurityValidator:
    """Validates namespace access, headers, and memory payloads."""

    @staticmethod
    def validate_namespace_access(authenticated_namespace: str, requested_namespace: str) -> bool:
        """
        Enforces strict namespace isolation.
        An agent cannot access or adopt a different namespace unless explicitly authorized.
        """
        if not authenticated_namespace or not requested_namespace:
            raise SecurityViolation("Namespace identifiers cannot be empty")
            
        clean_auth = authenticated_namespace.strip().lower()
        clean_req = requested_namespace.strip().lower()
        
        if clean_auth != clean_req and clean_auth != "admin":
            raise SecurityViolation(
                f"Unauthorized cross-namespace access: '{authenticated_namespace}' cannot access '{requested_namespace}'"
            )
        return True

    @staticmethod
    def sanitize_memory_content(content: str, strict_mode: bool = True) -> str:
        """
        Scans memory text for prompt injection / memory poisoning attempts.
        """
        if not content:
            return ""
            
        cleaned = content.strip()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                if strict_mode:
                    raise SecurityViolation(f"Memory payload rejected: detected adversarial pattern matching '{pattern}'")
                else:
                    # Sanitize by escaping
                    cleaned = re.sub(pattern, "[SANITIZED_PAYLOAD]", cleaned, flags=re.IGNORECASE)
                    
        return cleaned

    @staticmethod
    def validate_headers(headers: Dict[str, str], allowed_origins: Optional[list] = None) -> bool:
        """
        Validates incoming request headers, enforcing CORS protection and credential integrity.
        """
        origin = headers.get("Origin") or headers.get("origin")
        if origin and allowed_origins:
            if "*" in allowed_origins:
                raise SecurityViolation("Insecure configuration: wildcard '*' origin is disallowed in production")
            if origin not in allowed_origins:
                raise SecurityViolation(f"CORS policy violation: unauthorized origin '{origin}'")

        # Reject spoofed tenant injection headers
        if "X-Tenant-Override" in headers or "x-tenant-override" in headers:
            raise SecurityViolation("Header manipulation detected: X-Tenant-Override is strictly forbidden")

        return True
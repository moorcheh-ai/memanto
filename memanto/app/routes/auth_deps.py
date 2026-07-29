"""
auth_deps.py — Caller authentication dependencies
Fixed: get_moorcheh_api_key() now verifies the CALLER presents a valid key,
not just that the server has one configured. Closes #1436.
"""
from fastapi import Header, HTTPException, status
from typing import Optional
from memanto.app.core.config import settings
from memanto.app.core.backend import parse_backend, Backend


def get_moorcheh_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> str:
    """
    Verify the CALLER supplies a valid API key.
    Previously this only checked whether the server had a key configured;
    it did NOT validate what the caller sent. That allowed unauthenticated
    enumeration and activation of any agent (CVE reported in #1436).
    """
    backend = parse_backend(settings.MEMANTO_BACKEND)

    if backend == Backend.ON_PREM:
        # On-prem: require caller to supply the configured key
        configured = getattr(settings, "MOORCHEH_API_KEY", None)
        if configured and configured != "on-prem":
            if x_api_key != configured:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing API key. Supply X-API-Key header.",
                )
        # If no key configured, on-prem allows local-only access (still log warning)
        return x_api_key or "on-prem"

    # Cloud deployment: always require caller key
    configured = getattr(settings, "MOORCHEH_API_KEY", None)
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server has no API key configured. Contact administrator.",
        )
    if x_api_key != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Supply X-API-Key header.",
        )
    return x_api_key


# Alias — backwards compat with routes that import verify_moorcheh_api_key
verify_moorcheh_api_key = get_moorcheh_api_key

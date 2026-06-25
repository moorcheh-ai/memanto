"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.
"""

import hmac

from fastapi import Header, HTTPException

from memanto.app.models.session import Session
from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
    map_error_to_http_exception,
)


def get_moorcheh_api_key() -> str:
    """
    Get Moorcheh API key from server configuration.

    Returns:
        API key (or a placeholder string when running against the on-prem
        backend, which does not require an API key).

    Raises:
        HTTPException: If cloud is selected and no key is configured.
    """
    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    if parse_backend(settings.MEMANTO_BACKEND) == Backend.ON_PREM:
        # On-prem talks to localhost; routes that take ``moorcheh_api_key`` as
        # a dependency no longer use it for outbound calls (they go through
        # ``get_moorcheh_client()``), but the FastAPI signatures still need a
        # string. Return a placeholder so the dependency resolves.
        return "on-prem"

    if settings.MOORCHEH_API_KEY:
        return settings.MOORCHEH_API_KEY

    raise HTTPException(
        status_code=500,
        detail="Server misconfigured: MOORCHEH_API_KEY is not set",
    )


def _extract_request_api_key(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    """Extract an API key from supported request headers."""
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def verify_moorcheh_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    """
    Verify that the caller supplied the configured Moorcheh API key.

    Agent lifecycle routes mint session tokens and can delete local/remote
    namespaces, so they must authenticate the request itself instead of only
    checking that the server has a configured outbound Moorcheh key.
    """
    configured_key = get_moorcheh_api_key()
    provided_key = _extract_request_api_key(authorization, x_api_key)

    if configured_key == "on-prem":
        from memanto.app.config import settings

        expected_key = settings.MOORCHEH_API_KEY.strip()
        if not expected_key:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Server misconfigured: MOORCHEH_API_KEY is not set for API "
                    "authentication"
                ),
            )
    else:
        expected_key = configured_key.strip()

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Use Authorization: Bearer <MOORCHEH_API_KEY> or X-API-Key.",
        )
    if not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    return configured_key


def get_current_session(x_session_token: str | None = Header(None)) -> Session:
    """
    Get and validate current session

    Args:
        x_session_token: Session token header

    Returns:
        Validated Session

    Raises:
        HTTPException: If session is invalid or expired
    """
    if not x_session_token:
        raise HTTPException(
            status_code=401, detail="Missing session token. Use X-Session-Token header."
        )

    session_service = get_session_service()

    try:
        token_payload = session_service.validate_session(x_session_token)

        # Get session from storage
        session = session_service.get_session(token_payload.agent_id)
        if not session:
            raise SessionNotFoundError(
                f"Session for agent {token_payload.agent_id} not found"
            )

        # Auto-renew session if near expiry
        renewed = session_service.check_and_auto_renew(
            agent_id=token_payload.agent_id,
        )
        if renewed:
            session = renewed

        return session

    except (SessionExpiredError, SessionNotFoundError, InvalidSessionTokenError) as e:
        raise map_error_to_http_exception(e)

"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.
"""

from fastapi import Header, HTTPException

from memanto.app.models.session import Session
from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
    map_error_to_http_exception,
)


def _api_key_from_authorization(authorization: str | None) -> str | None:
    """Extract a Moorcheh API key from an Authorization header."""

    if not authorization:
        return None

    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Use 'Bearer <moorcheh_api_key>'.",
        )
    return parts[1].strip()


def get_moorcheh_api_key(authorization: str | None = Header(None)) -> str:
    """
    Get Moorcheh API key from request authorization or server configuration.

    Returns:
        API key supplied by ``Authorization: Bearer ...`` when present,
        otherwise the configured server key. On-prem returns a placeholder
        string because it does not require an API key.

    Raises:
        HTTPException: If the Authorization header is malformed, or if cloud is
        selected and no request/configured key is available.
    """
    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    if parse_backend(settings.MEMANTO_BACKEND) == Backend.ON_PREM:
        # On-prem talks to localhost. Routes still pass this dependency into
        # the backend-aware dispatcher, which ignores the placeholder for
        # on-prem clients.
        return "on-prem"

    if isinstance(authorization, str):
        header_api_key = _api_key_from_authorization(authorization)
        if header_api_key:
            return header_api_key

    if settings.MOORCHEH_API_KEY:
        return settings.MOORCHEH_API_KEY

    raise HTTPException(
        status_code=500,
        detail="Server misconfigured: MOORCHEH_API_KEY is not set",
    )


def verify_moorcheh_api_key(authorization: str | None = Header(None)) -> str:
    """
    Return request or configured Moorcheh API key.

    Runtime connectivity is validated at startup and via /health.
    """
    return get_moorcheh_api_key(authorization)


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

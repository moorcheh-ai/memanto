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


def get_moorcheh_api_key() -> str:
    """
    Get Moorcheh API key from server configuration.

    Returns:
        API key

    Raises:
        HTTPException: If no configured key is found
    """
    from memanto.app.config import settings

    if settings.MOORCHEH_API_KEY:
        return settings.MOORCHEH_API_KEY

    raise HTTPException(
        status_code=500,
        detail="Server misconfigured: MOORCHEH_API_KEY is not set",
    )


def verify_moorcheh_api_key() -> str:
    """
    Return configured Moorcheh API key.

    Runtime connectivity is validated at startup and via /health.
    """
    return get_moorcheh_api_key()


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

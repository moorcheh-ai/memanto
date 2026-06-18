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


def get_authorized_agent_ids(
    x_session_token: str | None = Header(None),
    x_session_tokens: str | None = Header(None),
) -> dict[str, str]:
    """
    Authorize a multi-agent (cross-namespace) request.

    The caller proves authorization for each agent by supplying that agent's
    session token, via ``X-Session-Tokens`` (comma-separated) and/or
    ``X-Session-Token``. Each token is validated (signature + expiry); the
    return value maps ``agent_id -> token`` for every token that validates.
    The route rejects any requested agent absent from this mapping.

    Raises:
        HTTPException: 401 if no tokens are supplied or none validate.
    """
    raw_tokens: list[str] = []
    if x_session_tokens:
        raw_tokens.extend(t.strip() for t in x_session_tokens.split(",") if t.strip())
    if x_session_token and x_session_token.strip():
        raw_tokens.append(x_session_token.strip())

    if not raw_tokens:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing session token(s). Provide X-Session-Tokens "
                "(comma-separated) and/or X-Session-Token."
            ),
        )

    session_service = get_session_service()
    authorized: dict[str, str] = {}
    for token in raw_tokens:
        try:
            payload = session_service.validate_session(token)
        except (SessionExpiredError, InvalidSessionTokenError):
            # Skip invalid/expired tokens — the route rejects any requested
            # agent that ends up without a valid token.
            continue
        # Match the token to a live session (existence + active status), like
        # get_current_session, so a valid JWT for a deleted/deactivated agent
        # is not accepted.
        session = session_service.get_session(payload.agent_id)
        if not session or not session.is_active():
            continue
        authorized[payload.agent_id] = token

    if not authorized:
        raise map_error_to_http_exception(
            InvalidSessionTokenError("No valid session tokens provided.")
        )

    return authorized

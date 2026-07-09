"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.
"""

from fastapi import Cookie, Header, HTTPException, Request, Response

from memanto.app.models.session import Session
from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
    map_error_to_http_exception,
)

SESSION_COOKIE_NAME = "memanto_session_token"


def set_session_cookie(
    response: Response, session_token: str, request: Request
) -> None:
    """Store the browser UI session token outside JavaScript-readable state.

    MEMANTO defaults to binding 0.0.0.0 with no built-in TLS (see docker-compose.yml
    and Settings.HOST), so a hardcoded Secure=True would silently stop browsers from
    ever sending the cookie back over the plain-HTTP deployment this ships with by
    default. Mark it Secure only when the current request actually arrived over HTTPS.
    """
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the browser UI session cookie."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


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


def get_current_session(
    request: Request,
    response: Response,
    x_session_token: str | None = Header(None),
    session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Session:
    """
    Get and validate current session

    Args:
        x_session_token: Session token header

    Returns:
        Validated Session

    Raises:
        HTTPException: If session is invalid or expired
    """
    session_token = x_session_token or session_cookie
    if not session_token:
        raise HTTPException(
            status_code=401, detail="Missing session token. Use X-Session-Token header."
        )

    session_service = get_session_service()

    try:
        token_payload = session_service.validate_session(session_token)

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
            # The renewed session gets a new session_id/token, invalidating
            # the one the caller just presented. Browser callers authenticate
            # via the HttpOnly cookie (never re-read the token in JS), so
            # without this the cookie goes stale and the very next request
            # fails signature/session_id validation.
            if session_cookie:
                set_session_cookie(response, renewed.session_token, request)

        return session

    except (SessionExpiredError, SessionNotFoundError, InvalidSessionTokenError) as e:
        raise map_error_to_http_exception(e)

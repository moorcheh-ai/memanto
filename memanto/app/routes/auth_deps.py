"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.

Security notes:
- Management endpoints require an explicit management credential.
- Session endpoints require a validated X-Session-Token or HttpOnly cookie.
- Management authorization does not trust client IP/loopback status.
"""

import secrets

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
    response: Response,
    session_token: str,
    request: Request,
) -> None:
    """Set the authenticated browser session cookie."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the authenticated browser session cookie."""
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
    )


def get_moorcheh_api_key() -> str:
    """Return the configured server-side Moorcheh credential."""
    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    backend = parse_backend(settings.MEMANTO_BACKEND)

    if backend == Backend.ON_PREM:
        return "on-prem"

    api_key = settings.MOORCHEH_API_KEY

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: MOORCHEH_API_KEY is not set",
        )

    return api_key


def _extract_presented_credential(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    """Extract a management credential from supported headers."""

    if x_api_key:
        value = x_api_key.strip()

        if value:
            return value

    if authorization:
        parts = authorization.strip().split(None, 1)

        if len(parts) == 2:
            scheme, credential = parts

            if (
                scheme.lower() == "bearer"
                and credential.strip()
            ):
                return credential.strip()

    return None


def _get_expected_management_credential() -> str | None:
    """Return the credential authorized to manage agents."""

    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    backend = parse_backend(settings.MEMANTO_BACKEND)

    if backend == Backend.ON_PREM:
        secret = (settings.MEMANTO_SECRET_KEY or "").strip()
        return secret or None

    api_key = (settings.MOORCHEH_API_KEY or "").strip()
    return api_key or None


def require_management_access(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(
        None,
        alias="X-Api-Key",
    ),
) -> str:
    """Authorize agent-management endpoints.

    Management access requires an explicit configured credential.

    Supported authentication:

        Authorization: Bearer <key>

    or:

        X-Api-Key: <key>

    No request IP address is treated as automatically trusted.
    """

    del request

    server_key = get_moorcheh_api_key()
    expected = _get_expected_management_credential()

    if expected is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Server misconfigured: management credential "
                "is unavailable"
            ),
        )

    presented = _extract_presented_credential(
        authorization,
        x_api_key,
    )

    if presented is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Unauthorized. Management credential required. "
                "Use Authorization: Bearer <key> or X-Api-Key."
            ),
        )

    if not secrets.compare_digest(
        presented,
        expected,
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Invalid management credential.",
        )

    return server_key


def verify_moorcheh_api_key(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(
        None,
        alias="X-Api-Key",
    ),
) -> str:
    """Compatibility wrapper for existing FastAPI dependencies."""

    return require_management_access(
        request=request,
        authorization=authorization,
        x_api_key=x_api_key,
    )


def get_current_session(
    request: Request,
    response: Response,
    x_session_token: str | None = Header(None),
    session_cookie: str | None = Cookie(
        None,
        alias=SESSION_COOKIE_NAME,
    ),
) -> Session:
    """Validate and return the authenticated session.

    The agent identity is always obtained from the validated session token.
    A caller cannot supply a separate agent_id through this dependency.
    """

    session_token = x_session_token or session_cookie

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing session token. "
                "Use X-Session-Token header."
            ),
        )

    session_service = get_session_service()

    try:
        token_payload = session_service.validate_session(
            session_token
        )

        # Identity comes only from the validated session.
        agent_id = token_payload.agent_id

        session = session_service.get_session(agent_id)

        if session is None:
            raise SessionNotFoundError(
                f"Session for agent {agent_id} not found"
            )

        renewed = session_service.check_and_auto_renew(
            agent_id=agent_id,
        )

        if renewed is not None:
            session = renewed

            if session_cookie:
                set_session_cookie(
                    response=response,
                    session_token=renewed.session_token,
                    request=request,
                )

        return session

    except (
        SessionExpiredError,
        SessionNotFoundError,
        InvalidSessionTokenError,
    ) as exc:
        raise map_error_to_http_exception(exc) from exc
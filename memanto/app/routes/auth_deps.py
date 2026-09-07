"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.
"""

from urllib.parse import urlsplit

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


def _extract_presented_credential(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    """Extract a client-presented management credential from request headers."""
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    return None


def _is_loopback_host(host: str | None) -> bool:
    """Return True when *host* is a loopback address (IPv4/IPv6/mapped)."""
    if not host:
        return False
    import ipaddress

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    ipv4_mapped = getattr(addr, "ipv4_mapped", None)
    return ipv4_mapped is not None and ipv4_mapped.is_loopback


def _is_loopback_origin(origin: str | None) -> bool:
    """Return True when a browser Origin points at the local Memanto host."""
    if not origin or not isinstance(origin, str):
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.hostname == "localhost" or _is_loopback_host(parsed.hostname)


def _is_loopback_host_header(host: str | None) -> bool:
    """Return True when an HTTP Host header names a loopback interface."""
    if not host or not isinstance(host, str):
        return False
    try:
        hostname = urlsplit(f"//{host}").hostname
    except ValueError:
        return False
    return hostname == "localhost" or _is_loopback_host(hostname)


def _is_cross_site_browser_request(request: Request) -> bool:
    """Detect browser requests that must not inherit loopback trust."""
    origin = request.headers.get("origin")
    if origin is not None and isinstance(origin, str):
        return not _is_loopback_origin(origin)

    fetch_site = request.headers.get("sec-fetch-site", "")
    if isinstance(fetch_site, str):
        fetch_site = fetch_site.strip().lower()
    else:
        fetch_site = ""
    return fetch_site in {"cross-site", "same-site"}


def require_management_access(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Authorize agent-lifecycle / management endpoints.

    MEMANTO is a single-tenant companion service. Agent create/list/delete/
    activate endpoints previously only checked that the *server* had a
    configured API key, not that the *caller* was authorized. Combined with
    the default ``HOST=0.0.0.0`` bind (see Settings / docker-compose), any
    network peer could create agents, activate sessions, and obtain
    ``session_token`` values for memory read/write.

    Access is granted when either:

    1. The caller presents the server management credential
       (``Authorization: Bearer <key>`` or ``X-Api-Key``), matched with
       ``secrets.compare_digest`` against the configured cloud API key, or
       against ``MEMANTO_SECRET_KEY`` for on-prem; or
    2. The request originates from the loopback interface (local desktop
       CLI / browser UX without forcing every local call to attach a key).

    Returns the server-side Moorcheh credential string used by downstream
    service calls (same contract as ``get_moorcheh_api_key``).
    """
    import secrets

    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    server_key = get_moorcheh_api_key()
    presented = _extract_presented_credential(authorization, x_api_key)
    backend = parse_backend(settings.MEMANTO_BACKEND)

    expected: str | None
    if backend == Backend.ON_PREM:
        # On-prem has no cloud API key; use the JWT/session secret as the
        # management shared secret when one is configured.
        expected = (settings.MEMANTO_SECRET_KEY or "").strip() or None
    else:
        expected = server_key if server_key and server_key != "on-prem" else None

    if presented and expected and secrets.compare_digest(presented, expected):
        return server_key

    client_host = request.client.host if request.client else None
    if (
        _is_loopback_host(client_host)
        and _is_loopback_host_header(request.headers.get("host"))
        and not _is_cross_site_browser_request(request)
    ):
        return server_key

    raise HTTPException(
        status_code=401,
        detail=(
            "Unauthorized. Agent management endpoints require either a "
            "loopback client or a valid management credential "
            "(Authorization: Bearer <key> or X-Api-Key)."
        ),
    )


def verify_moorcheh_api_key(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Authorize management access and return the server Moorcheh credential.

    Kept as a thin wrapper so existing ``Depends(verify_moorcheh_api_key)``
    call sites pick up the new authorization rules without signature churn
    at every route.
    """
    return require_management_access(request, authorization, x_api_key)


def get_current_session(
    request: Request,
    response: Response,
    x_session_token: str | None = Header(None),
    session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> Session:
    """
    Get and validate current session

    Args:
        x_session_token: Session token header
        authorization: Bearer management credential (for auto-recreate)
        x_api_key: Management credential header (for auto-recreate)

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
            # API clients authenticate with the request header instead of a
            # cookie. Return the replacement token on the response so they can
            # use it after auto-renewal invalidates the presented token.
            if x_session_token:
                response.headers["X-Session-Token"] = renewed.session_token

        return session

    except SessionExpiredError as e:
        # The presented token belongs to a session that has fully lapsed.
        # With SESSION_AUTO_RECREATE_ENABLED the caller gets a fresh session
        # on this first operation — but only after passing the same
        # management-access check as explicit activation (valid API key or
        # loopback origin), so a stolen stale token alone is worthless.
        recreated = _maybe_auto_recreate_session(
            request=request,
            response=response,
            session_token=session_token,
            x_session_token=x_session_token,
            session_cookie=session_cookie,
            authorization=authorization,
            x_api_key=x_api_key,
        )
        if recreated is None:
            raise map_error_to_http_exception(e)
        return recreated

    except (SessionNotFoundError, InvalidSessionTokenError) as e:
        raise map_error_to_http_exception(e)


def _maybe_auto_recreate_session(
    request: Request,
    response: Response,
    session_token: str,
    x_session_token: str | None,
    session_cookie: str | None,
    authorization: str | None,
    x_api_key: str | None,
) -> Session | None:
    """Attempt transparent recreation of an expired session.

    Returns the fresh Session, or None when recreation does not apply
    (disabled by config, terminated/logout session, superseded token) or is
    not authorized — in which case the original expiry error surfaces.
    """
    try:
        require_management_access(request, authorization, x_api_key)
    except HTTPException:
        return None

    recreated = get_session_service().check_and_auto_recreate(session_token)
    if recreated is None:
        return None

    # Mirror the auto-renewal handoff: refresh the browser cookie and/or
    # return the replacement token so the next request authenticates.
    if session_cookie:
        set_session_cookie(response, recreated.session_token, request)
    if x_session_token:
        response.headers["X-Session-Token"] = recreated.session_token

    return recreated

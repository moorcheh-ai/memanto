import logging
from urllib.parse import urlsplit, urlunsplit

from fastapi import Cookie, Header, HTTPException, Request, Response

from memanto.app.config import is_loopback_host
from memanto.app.models.session import Session
from memanto.app.services.session_service import get_session_service
from memanto.app.utils.client_identity import set_memanto_session
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
    map_error_to_http_exception,
)

SESSION_COOKIE_NAME = "memanto_session_token"

logger = logging.getLogger(__name__)


def _sanitize_log_value(value: object) -> str:
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in str(value))


def _redact_and_sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    return _sanitize_log_value(
        urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    )


def set_session_cookie(
    response: Response, session_token: str, request: Request
) -> None:
    secure = request.url.scheme == "https"
    peer_host = request.client.host if request.client else None
    if not secure and (
        not is_loopback_host(peer_host) or _has_forwarded_non_loopback(request)
    ):
        logger.warning(
            "Issuing the browser UI session cookie over plain HTTP from %s. "
            "Any network peer that can reach this port can intercept it and "
            "gain full memory read/write for the active agent. Terminate TLS "
            "in front of Memanto or bind to a loopback address.",
            _redact_and_sanitize_url(str(request.url)),
        )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def get_moorcheh_api_key() -> str:
    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    if parse_backend(settings.MEMANTO_BACKEND) == Backend.ON_PREM:
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
    if isinstance(x_api_key, str) and x_api_key.strip():
        return x_api_key.strip()
    if isinstance(authorization, str):
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    return None


def _origin_is_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin or not isinstance(origin, str):
        return True  # non-browser caller (CLI, curl, SDK) or mock/test request
    from memanto.app.config import settings

    origin_stripped = origin.rstrip("/")
    allowed = [o.rstrip("/") for o in settings.ALLOWED_ORIGINS]

    if origin_stripped in allowed:
        return True

    if settings.CORS_ORIGIN_REGEX:
        import re

        if re.match(settings.CORS_ORIGIN_REGEX, origin_stripped):
            return True

    return False


def _require_allowed_origin(request: Request) -> None:
    if not _origin_is_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="Origin not allowed for management endpoints",
        )


def _is_loopback_origin(origin: str | None) -> bool:
    if not origin or not isinstance(origin, str):
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.hostname == "localhost" or is_loopback_host(parsed.hostname)


def _is_loopback_host_header(host: str | None) -> bool:
    if not host or not isinstance(host, str):
        return False
    try:
        hostname = urlsplit(f"//{host}").hostname
    except ValueError:
        return False
    return hostname == "localhost" or is_loopback_host(hostname)


def _is_cross_site_browser_request(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is not None and isinstance(origin, str):
        return not _is_loopback_origin(origin)

    fetch_site = request.headers.get("sec-fetch-site", "")
    if isinstance(fetch_site, str):
        fetch_site = fetch_site.strip().lower()
    else:
        fetch_site = ""
    return fetch_site in {"cross-site", "same-site"}


def _has_forwarded_non_loopback(request: Request) -> bool:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        for ip in xff.split(","):
            cleaned = ip.strip()
            if cleaned and not is_loopback_host(cleaned):
                return True

    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        cleaned = x_real_ip.strip()
        if cleaned and not is_loopback_host(cleaned):
            return True

    forwarded = request.headers.get("forwarded")
    if forwarded:
        for item in forwarded.split(";"):
            item = item.strip()
            if item.lower().startswith("for="):
                val = item[4:].strip().strip('"').strip("[]")
                if ":" in val and not val.startswith(":"):
                    try:
                        import ipaddress

                        ipaddress.ip_address(val)
                    except ValueError:
                        val = val.rsplit(":", 1)[0].strip()
                if val and not is_loopback_host(val):
                    return True

    return False


def require_management_access(
    request: Request,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    import secrets

    from memanto.app.clients.backend import Backend, parse_backend
    from memanto.app.config import settings

    server_key = get_moorcheh_api_key()
    presented = _extract_presented_credential(authorization, x_api_key)
    backend = parse_backend(settings.MEMANTO_BACKEND)

    expected: str | None
    if backend == Backend.ON_PREM:
        expected = (settings.MEMANTO_SECRET_KEY or "").strip() or None
    else:
        expected = server_key if server_key and server_key != "on-prem" else None

    if presented and expected and secrets.compare_digest(presented, expected):
        return server_key

    _require_allowed_origin(request)

    client_host = request.client.host if request.client else None
    if (
        is_loopback_host(client_host)
        and _is_loopback_host_header(request.headers.get("host"))
        and not _is_cross_site_browser_request(request)
        and not _has_forwarded_non_loopback(request)
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
    return require_management_access(request, authorization, x_api_key)


def get_current_session(
    request: Request,
    response: Response,
    x_session_token: str | None = Header(None),
    session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> Session:
    session_token = x_session_token or session_cookie
    if not session_token:
        raise HTTPException(
            status_code=401, detail="Missing session token. Use X-Session-Token header."
        )

    if session_cookie and not x_session_token:
        client_host = request.client.host if request.client else None
        if (
            not is_loopback_host(client_host)
            or not _is_loopback_host_header(request.headers.get("host"))
            or _is_cross_site_browser_request(request)
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Cookie-authenticated session requests must originate "
                    "from the loopback interface targeting a loopback Host."
                ),
            )

    session_service = get_session_service()

    try:
        token_payload = session_service.validate_session(session_token)

        session = session_service.get_session(token_payload.agent_id)
        if not session:
            raise SessionNotFoundError(
                f"Session for agent {token_payload.agent_id} not found"
            )

        renewed = session_service.check_and_auto_renew(
            agent_id=token_payload.agent_id,
        )
        if renewed:
            session = renewed

            if session_cookie:
                set_session_cookie(response, renewed.session_token, request)

            if x_session_token:
                response.headers["X-Session-Token"] = renewed.session_token

        set_memanto_session(session.session_id)
        return session

    except SessionExpiredError as e:
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
    try:
        require_management_access(request, authorization, x_api_key)
    except HTTPException:
        return None

    recreated = get_session_service().check_and_auto_recreate(session_token)
    if recreated is None:
        return None

    if session_cookie:
        set_session_cookie(response, recreated.session_token, request)
    if x_session_token:
        response.headers["X-Session-Token"] = recreated.session_token

    return recreated

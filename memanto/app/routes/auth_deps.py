"""
Authentication Dependencies for V2 API

Shared authentication utilities to avoid circular imports.
"""

import ipaddress
from urllib.parse import urlsplit

from fastapi import Cookie, Header, HTTPException, Request, Response

from memanto.app.config import settings

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


def _request_uses_forwarded_headers(request: Request) -> bool:
    """Return True when the caller arrived through a reverse proxy.

    ``X-Forwarded-For`` / ``X-Real-IP`` / ``X-Forwarded-Host`` / ``Forwarded``
    are only emitted by proxies, never by a direct client. Their presence is
    the reliable signal that ``request.client.host`` is the *proxy's* address,
    not the originating peer's.
    """
    return any(
        h in request.headers
        for h in ("x-forwarded-for", "x-real-ip", "x-forwarded-host", "forwarded")
    )


def _is_trusted_proxy(client_host: str | None) -> bool:
    """Return True when *client_host* is an explicitly configured trusted proxy.

    A trusted proxy is allowed to set forwarding headers on behalf of the real
    client, so loopback trust may still apply for connections originating from
    it. Defaults to no trusted proxies (empty ``TRUSTED_PROXIES``).
    """
    if not client_host:
        return False
    try:
        peer = ipaddress.ip_address(client_host)
    except ValueError:
        # A hostname (not an IP) is never a trusted proxy entry.
        return False
    for entry in settings.TRUSTED_PROXIES:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if peer in ipaddress.ip_network(entry, strict=False):
                    return True
            elif peer == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


# --- Forwarded-header effective-client resolution (CWE-290 hardening) ---
#
# A trusted reverse proxy is permitted to set forwarding headers, but "trusted
# proxy" must never mean "trusted client". When a request arrives from a
# configured trusted proxy we resolve the *effective* originating client from
# the forwarding headers and only restore loopback trust when that client is
# itself unambiguously loopback and every forwarding header agrees.


_XFF_MALFORMED = object()


def _to_ip(text: str):
    """Parse *text* into an ``ipaddress`` object, or None when it is not an IP."""
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def _strip_ip_port(token: str):
    """Return the IP a header token names, dropping any ``[ipv6]:port`` / IPv4:port.

    Returns an ``ipaddress`` object, or None when the token is not a valid IP
    (e.g. an unparsable host or obfuscated forward token).
    """
    token = (token or "").strip()
    if not token:
        return None
    if token.startswith("["):
        end = token.find("]")
        if end == -1:
            return None
        return _to_ip(token[1:end])
    if ":" in token:
        # Either a bare IPv6 address, or IPv4:port. Try the whole token as an IP
        # first; on failure assume an IPv4 host with a trailing port.
        as_ip = _to_ip(token)
        if as_ip is not None:
            return as_ip
        host = token.rsplit(":", 1)[0]
        return _to_ip(host)
    return _to_ip(token)


def _parse_x_forwarded_for(xff: str) -> list:
    """Split ``X-Forwarded-For`` into parsed IP entries (None marks malformed)."""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if not parts:
        return [None]
    return [_strip_ip_port(p) for p in parts]


def _effective_xff_client(entries: list, peer_host: str):
    """Resolve the effective client from ``X-Forwarded-For`` entries.

    The effective client is the *rightmost* entry: the peer the last proxy
    received the connection from. Using the rightmost entry prevents an
    untrusted client from prepending a spoofed loopback address that a naive
    leftmost parse would honour. If the rightmost entry is the proxy's own
    address (it appended its own peer), step one entry left to reach the real
    client. A single entry is taken verbatim (the proxy overwrote the header).
    """
    if any(e is None for e in entries):
        return _XFF_MALFORMED
    if len(entries) == 1:
        return entries[0]
    if str(entries[-1]) == peer_host:
        # Proxy appended its own peer address; the real client is one left.
        return entries[-2]
    return entries[-1]


def _parse_forwarded_for(forwarded: str):
    """Extract the client IP from a standard ``Forwarded`` header ``for=`` value.

    Returns an ``ipaddress`` object, or None when the header yields no concrete
    IP (the obfuscated ``for="_host"`` / ``for="unknown"`` forms count as
    unresolvable and therefore untrusted).
    """
    for part in forwarded.split(";"):
        part = part.strip()
        if not part.lower().startswith("for="):
            continue
        val = part[len("for="):].strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        if val.startswith("_") or val.lower() == "unknown":
            return None
        return _strip_ip_port(val)
    return None


def _resolve_trusted_proxy_client(request: Request):
    """Decide whether a request from a trusted proxy may inherit loopback trust.

    The immediate peer is already known to be a configured trusted proxy. We
    must still pin down the *effective* client it forwards for and confirm that
    client is itself loopback and that all forwarding headers agree.

    Returns:
        ``("allow", ipaddress)`` when the effective client is unambiguously a
        loopback address with no conflicting/malformed headers; otherwise
        ``("deny", reason)``.
    """
    xff = request.headers.get("x-forwarded-for")
    x_real_ip = request.headers.get("x-real-ip")
    forwarded = request.headers.get("forwarded")
    peer_host = request.client.host if request.client else ""

    resolved: dict = {}

    if xff is not None:
        effective = _effective_xff_client(_parse_x_forwarded_for(xff), peer_host)
        if effective is _XFF_MALFORMED:
            return ("deny", "malformed x-forwarded-for")
        resolved["x-forwarded-for"] = effective

    if x_real_ip is not None:
        ip = _strip_ip_port(x_real_ip)
        if ip is None:
            return ("deny", "malformed x-real-ip")
        resolved["x-real-ip"] = ip

    if forwarded is not None:
        ip = _parse_forwarded_for(forwarded)
        if ip is None:
            return ("deny", "malformed forwarded")
        resolved["forwarded"] = ip

    if not resolved:
        return ("deny", "no resolvable client ip")

    # Headers that are present must agree on the client IP.
    if len(set(resolved.values())) > 1:
        return ("deny", "conflicting forwarding headers")

    client_ip = next(iter(resolved.values()))
    if not client_ip.is_loopback:
        return ("deny", "effective client is not loopback")
    return ("allow", client_ip)


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

    When a loopback request arrived *through* a reverse proxy, loopback trust
    is only restored if the immediate peer is an explicitly configured trusted
    proxy AND the effective client it forwards for (resolved from
    ``X-Forwarded-For`` / ``X-Real-IP`` / ``Forwarded``) is itself unambiguously
    a loopback address with no conflicting/malformed headers. A trusted proxy
    is not a trusted client: a public-IP forwarded client behind a trusted
    proxy is rejected (CWE-290).

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
    loopback_trusted = (
        _is_loopback_host(client_host)
        and _is_loopback_host_header(request.headers.get("host"))
        and not _is_cross_site_browser_request(request)
    )
    if loopback_trusted:
        uses_proxy_headers = _request_uses_forwarded_headers(request)
        if uses_proxy_headers and not _is_trusted_proxy(client_host):
            # An untrusted peer is presenting forwarding headers, trying to
            # claim a proxied/loopback origin. Refuse the spoof (CWE-290).
            loopback_trusted = False
        elif uses_proxy_headers and _is_trusted_proxy(client_host):
            # The immediate peer is a configured trusted proxy. A trusted proxy
            # is NOT a trusted client: only inherit loopback trust when the
            # *effective* client it forwards for is itself unambiguously a
            # loopback address and all forwarding headers agree.
            verdict, _client_ip = _resolve_trusted_proxy_client(request)
            if verdict != "allow":
                loopback_trusted = False
        elif _is_trusted_proxy(client_host):
            # Trusted proxy but no forwarding headers: the effective client
            # cannot be determined, so do not restore loopback trust.
            loopback_trusted = False
    if loopback_trusted:
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

"""ASGI middleware for MEMANTO.

Small, dependency-light middleware that Starlette does not provide in the
version pinned by this project.
"""

import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from memanto.app.config import is_loopback_host

logger = logging.getLogger(__name__)

_HTTPS = "https"
_HTTP = "http"
_PROTO_HEADER = "x-forwarded-proto"


def _normalize_peer_address(peer: str) -> str:
    """Return the canonical form of a connected peer host.

    Dual-stack servers report IPv4 connections through an IPv6-wildcard bind as
    IPv4-mapped addresses (``::ffff:10.0.0.5``). Unwrapping them keeps the
    connection peer comparable with the allowlist entries returned by
    ``Settings.proxy_allowed_ips`` (which canonicalizes the same way), so a
    trusted proxy seen through either address family matches.
    """
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    return peer


class TrustedProxySchemeMiddleware:
    """Rewrite the request scheme from ``X-Forwarded-Proto``.

    MEMANTO often sits behind a reverse proxy that terminates TLS (Ingress,
    Caddy, nginx, ...). Without this, ``request.url.scheme`` stays ``http`` for
    proxied requests and the browser UI session cookie is emitted without the
    ``Secure`` flag even though the browser talks HTTPS.

    Only peers listed in the ``allowed_ips`` allowlist are trusted to set the
    forwarding header; any other peer is untrusted, so a random network client
    cannot force ``https`` (or spoof ``http``) merely by sending a header.
    When a forwarded scheme is present from an untrusted peer, it is ignored
    and the scheme is reset to ``http``. That reset only holds when
    ``scope["client"]`` still identifies the direct connection peer: Uvicorn's
    built-in proxy-header handling rewrites both the scheme *and* the client
    address from forwarding headers, so it must be disabled (``proxy_headers=
    False`` / ``--no-proxy-headers``) for the allowlist to be meaningful.

    Every built-in launch path already disables it (``memanto serve``/``ui``,
    the ``__main__`` entrypoint, and the Dockerfile command). A direct
    ``uvicorn memanto.app.main:app`` launch must also pass ``--no-proxy-headers``;
    otherwise an untrusted peer can inject ``X-Forwarded-For`` set to an
    allowlisted address, have Uvicorn rewrite ``scope["client"]``, and then
    forge ``X-Forwarded-Proto: https`` to bypass ``MEMANTO_REQUIRE_SECURE``.

    When ``require_secure`` is set, requests whose final scheme is still
    ``http`` are rejected with ``403`` before reaching the application, so the
    enforcement applies on every entrypoint — including ``uvicorn
    app.main:app``, which never runs the startup guard. The deployer's proxy
    must overwrite any client-supplied ``X-Forwarded-Proto`` before it reaches
    MEMANTO.

    Requests from a verified loopback peer escape the ``require_secure``
    rejection, matching ``check_secure_deployment``'s startup guard: the
    local browser UI and in-container health checks (e.g. the Dockerfile
    ``/ready`` probe) must keep working on plain HTTP without disabling secure
    mode for the network-facing deployment.
    """

    def __init__(
        self, app: Any, allowed_ips: list[str], require_secure: bool = False
    ) -> None:
        self.app = app
        self.allowed_ips = {ip.strip() for ip in allowed_ips if ip and ip.strip()}
        self.require_secure = require_secure

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") == "http":
            client = scope.get("client")
            peer = _normalize_peer_address(client[0] if client else "")
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            proto = (headers.get(_PROTO_HEADER) or "").strip().lower()
            if peer in self.allowed_ips:
                if proto in (_HTTP, _HTTPS):
                    scope["scheme"] = proto
            elif proto:
                scope["scheme"] = _HTTP
            if (
                self.require_secure
                and scope.get("scheme") == _HTTP
                and not is_loopback_host(peer)
            ):
                await self._reject_plain_http(send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject_plain_http(
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        body = (
            b"403 Forbidden: plain HTTP is not allowed while "
            b"MEMANTO_REQUIRE_SECURE is enabled. Terminate TLS at a reverse "
            b"proxy and list it in MEMANTO_PROXY_ALLOWED_IPS."
        )
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

"""ASGI middleware for MEMANTO.

Small, dependency-light middleware that Starlette does not provide in the
version pinned by this project.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

_HTTPS = "https"
_HTTP = "http"
_PROTO_HEADER = "x-forwarded-proto"


class TrustedProxySchemeMiddleware:
    """Rewrite the request scheme from ``X-Forwarded-Proto``.

    MEMANTO often sits behind a reverse proxy that terminates TLS (Ingress,
    Caddy, nginx, ...). Without this, ``request.url.scheme`` stays ``http`` for
    proxied requests and the browser UI session cookie is emitted without the
    ``Secure`` flag even though the browser talks HTTPS.

    Only peers listed in the ``allowed_ips`` allowlist are trusted to set the
    forwarding header; for anyone else it is ignored, so a random network
    client cannot force ``https`` (or spoof ``http``) merely by sending a
    header. The deployer's proxy must overwrite any client-supplied
    ``X-Forwarded-Proto`` before it reaches MEMANTO.
    """

    def __init__(self, app: Any, allowed_ips: list[str]) -> None:
        self.app = app
        self.allowed_ips = {ip.strip() for ip in allowed_ips if ip and ip.strip()}

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") == "http":
            client = scope.get("client")
            peer = client[0] if client else ""
            if peer and peer in self.allowed_ips:
                headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in scope.get("headers", [])
                }
                proto = (headers.get(_PROTO_HEADER) or "").strip().lower()
                if proto in (_HTTP, _HTTPS):
                    scope["scheme"] = proto
        await self.app(scope, receive, send)

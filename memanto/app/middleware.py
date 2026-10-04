import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from memanto.app.config import is_loopback_host

logger = logging.getLogger(__name__)

_HTTPS = "https"
_HTTP = "http"
_PROTO_HEADER = "x-forwarded-proto"
_FORWARDING_HEADERS = frozenset(
    (_PROTO_HEADER, "x-forwarded-for", "x-real-ip", "forwarded")
)


def _normalize_peer_address(peer: str) -> str:
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    return peer


class TrustedProxySchemeMiddleware:
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
                # A local reverse proxy is not a local client. Header presence
                # only removes the plaintext exemption; it never grants trust
                # or changes the scheme for an untrusted proxy.
                and (
                    not is_loopback_host(peer)
                    or not _FORWARDING_HEADERS.isdisjoint(headers)
                )
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

"""TrustedProxySchemeMiddleware: forwarded-proto trust and MEMANTO_REQUIRE_SECURE."""

import asyncio

import pytest

from memanto.app.middleware import TrustedProxySchemeMiddleware


def _call(peer, proto=None, allowed_ips=(), require_secure=True):
    seen = {}
    sent = []

    async def app(scope, receive, send):
        seen["scheme"] = scope["scheme"]
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        sent.append(message)

    headers = [(b"x-forwarded-proto", proto.encode())] if proto else []
    scope = {
        "type": "http",
        "scheme": "http",
        "client": (peer, 1234),
        "headers": headers,
    }
    middleware = TrustedProxySchemeMiddleware(
        app, allowed_ips=list(allowed_ips), require_secure=require_secure
    )
    asyncio.run(middleware(scope, None, send))
    return sent[0]["status"], seen.get("scheme")


def test_direct_loopback_plain_http_is_allowed():
    assert _call("127.0.0.1") == (200, "http")


def test_remote_plain_http_is_rejected():
    assert _call("203.0.113.5")[0] == 403


@pytest.mark.parametrize("proxy", ["127.0.0.1", "10.0.0.5"])
def test_trusted_proxy_https_is_allowed(proxy):
    assert _call(proxy, "https", allowed_ips=[proxy]) == (200, "https")


@pytest.mark.parametrize("proxy", ["127.0.0.1", "10.0.0.5"])
def test_trusted_proxy_plain_http_is_rejected(proxy):
    assert _call(proxy, "http", allowed_ips=[proxy])[0] == 403


def test_untrusted_forwarded_https_is_not_believed():
    assert _call("203.0.113.5", "https", allowed_ips=["10.0.0.5"])[0] == 403


def test_require_secure_off_keeps_plain_http():
    assert _call("203.0.113.5", require_secure=False) == (200, "http")


@pytest.mark.parametrize("allowed, expected", [([], True), (["10.0.0.5"], False)])
def test_serve_hands_forwarded_headers_to_memanto(monkeypatch, allowed, expected):
    from memanto.app.config import settings
    from memanto.cli.commands.core import _uvicorn_proxy_headers

    monkeypatch.setattr(settings, "MEMANTO_PROXY_ALLOWED_IPS", allowed)
    assert _uvicorn_proxy_headers() is expected

"""The plaintext exemption applies to direct loopback clients, not proxies."""

import asyncio

import pytest

from memanto.app.middleware import TrustedProxySchemeMiddleware


@pytest.mark.parametrize(
    "peer,scheme,headers,allowed_ips,require_secure,expected",
    [
        ("127.0.0.1", "http", [], [], True, 204),
        ("::1", "http", [], [], True, 204),
        ("127.0.0.1", "http", [(b"x-forwarded-proto", b"http")], ["127.0.0.1"], True, 403),
        ("127.0.0.1", "http", [(b"x-forwarded-for", b"192.0.2.1")], [], True, 403),
        ("::1", "http", [(b"x-real-ip", b"192.0.2.1")], [], True, 403),
        ("::ffff:127.0.0.1", "http", [(b"forwarded", b"for=192.0.2.1;proto=http")], [], True, 403),
        ("127.0.0.1", "http", [(b"x-forwarded-for", b"")], [], True, 403),
        ("127.0.0.1", "http", [(b"x-forwarded-proto", b"https")], [], True, 403),
        ("127.0.0.1", "http", [(b"x-forwarded-proto", b"https")], ["127.0.0.1"], True, 204),
        ("192.0.2.1", "http", [], [], True, 403),
        ("192.0.2.1", "https", [], [], True, 204),
        ("127.0.0.1", "http", [(b"x-forwarded-proto", b"http")], ["127.0.0.1"], False, 204),
    ],
)
def test_secure_proxy_loopback(peer, scheme, headers, allowed_ips, require_secure, expected):
    calls = []
    sent = []

    async def app(scope, receive, send):
        calls.append(scope["scheme"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "scheme": scheme, "client": (peer, 1234), "headers": headers}
    middleware = TrustedProxySchemeMiddleware(app, allowed_ips, require_secure)
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == expected
    assert len(calls) == (1 if expected == 204 else 0)
    assert sent[-1]["type"] == "http.response.body"
    if expected == 403:
        declared = dict(sent[0]["headers"])[b"content-length"]
        assert int(declared) == len(sent[-1]["body"])

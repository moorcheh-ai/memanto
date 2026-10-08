# Secure-transport loopback proxy bypass

Continuation of the existing #1852 submission; no separate prize claim.

## Preconditions and flaw

The operator opts into `MEMANTO_REQUIRE_SECURE=true` and places a reverse proxy on the same host as Memanto. A plaintext client request reaches the application through that proxy. The ASGI TCP peer is therefore a loopback address even though the client-to-proxy connection is not local or encrypted.

At source `79f6ee17c06496b53a2652a8033ba77b3d83f599`, `TrustedProxySchemeMiddleware` checks only the TCP peer when granting the plaintext exception. Even with the loopback proxy explicitly trusted and `X-Forwarded-Proto: http`, the request reaches the downstream application. Forwarded client addresses do not remove that exception either.

This defeats the operator's opted-in transport restriction. It does not itself bypass session or management authorization. With an authenticated request, application data would still travel over the plaintext client-to-proxy hop. No real credentials, live service, or network interception were used in the reproduction.

## Minimal reproduction

Use the maintained regression file:

```sh
python -m pytest -q tests/test_secure_proxy_loopback.py
```

Its ASGI application records invocation and returns 204. The central case uses `client=("127.0.0.1", 1234)`, `scheme="http"`, header `X-Forwarded-Proto: http`, `allowed_ips=["127.0.0.1"]`, and `require_secure=True`. The old middleware invokes the application and returns 204; the repair returns 403 without invoking it. Related cases cover X-Forwarded-For, X-Real-IP, RFC Forwarded, an IPv4-mapped loopback peer, empty forwarding fields, and an untrusted HTTPS claim.

## Repair and compatibility

Only direct loopback HTTP requests without forwarding indicators retain the exception. Presence of a forwarding field removes that exemption; its contents never establish trusted-proxy identity or change scheme handling. The existing allowed-IP check remains the only authority for `X-Forwarded-Proto`.

Direct loopback HTTP remains supported. Trusted-proxy HTTPS, direct remote HTTPS, and `require_secure=False` retain their existing behavior. Remote plaintext remains rejected. Proxied local HTTP also now requires TLS when this option is enabled; operators needing a local plaintext development proxy can leave the option disabled. A proxy must supply accurate forwarding metadata and must not pass untrusted client assertions through as authoritative values. A proxy that strips all forwarding indicators cannot be distinguished from a direct local client by this exemption.

## Executed evidence — October 4, 2026

The complete original middleware bytes were verified against Git blob `304d30c7d3a4ebe65f0f9930c1a2e5938a8efbbb`. One bounded before/after check ran the complete production ASGI middleware and its exact production `is_loopback_host` helper with twelve controlled requests. Configuration loading was isolated to avoid reading local .env files or initializing providers.

- Original: 6 failed / 6 passed in 0.06 seconds. Each failure admitted a request expected to be rejected.
- Repaired: 12 passed in 0.05 seconds.
- Rejections prove downstream invocation count zero and a correctly framed 403 response.

These are in-process ASGI results, not full FastAPI startup, real reverse-proxy deployment, browser, TLS negotiation, live backend, or end-to-end interception evidence. No full suite, package installation, or hosted build was run for this change. The earlier composition result remains bound to its own source revision.

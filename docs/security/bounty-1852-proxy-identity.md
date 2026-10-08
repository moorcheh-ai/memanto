# Forwarded requests with unknown client identity inherit local management trust

Continuation of the existing #1852 submission, not a separate prize claim.

## Preconditions and impact

A local reverse proxy forwards an external request with a loopback upstream Host. It supplies forwarding metadata, such as `X-Forwarded-Proto: https`, but does not supply a usable client address. The original `_has_forwarded_non_loopback` returns false: absence of a recognized remote address is treated as proof of locality. `require_management_access` then grants the loopback exemption without a management credential. Empty forwarding-address fields have the same problem.

The dependency protects agent lifecycle/management operations. The demonstrated effect is unauthorized admission through that actual dependency into a protected FastAPI handler, not an executed remote agent takeover. It requires the stated proxy/Host/header combination; direct remote connections and correctly supplied remote client addresses already fail. TLS alone does not establish client identity, so this is distinct from the plaintext-policy repair in `8136b954`.

## Repair

Track whether forwarding is indicated and whether a usable client identity was supplied. Empty X-Forwarded-For hops, empty X-Real-IP, and Forwarded fields without a for parameter cannot grant local trust. X-Forwarded-* metadata without any usable client identity also fails the exemption. Existing quoted-node parsing, repeated-field handling and remote-node rejection are preserved. Direct loopback clients, explicit all-loopback client metadata and valid management credentials keep their existing admission behavior.

Operators must still ensure their proxy replaces or correctly extends untrusted client-address headers. This change does not make attacker-controlled loopback assertions trustworthy, identify a proxy that strips all forwarding indicators, or replace network access controls. The shared helper also remains used by the cookie/local-session checks; those other service paths were not independently executed in this continuation.

## Reproduction and executed evidence — October 4, 2026

```sh
python -m pytest -q tests/test_management_forwarded_identity.py
```

The central case sends POST `/management` through a real FastAPI dependency with peer `127.0.0.1`, HTTPS URL/loopback Host, and only `X-Forwarded-Proto: https`. Before the patch the handler runs and returns 204; after the patch it is not called and the dependency returns 401. A wrong management key no longer falls through to this unknown-origin exemption either.

One bounded before/after run loaded the complete production auth module, verified against original Git blob `62c275eebea3785a3bee6065de70e6105b3622ab`, using synthetic on-prem settings and inert unused session/provider imports. HTTPX's in-process ASGI transport exercised actual FastAPI dependency resolution, credential comparison, Host/Origin checks and forwarding helpers. No network connection or real credential was used.

- Original: 10 failed / 14 passed, 0.17 seconds. All ten failures admitted a request expected to be denied.
- Repaired: 24 passed, 0.13 seconds. Denial cases also assert that the protected handler was never invoked.
- Both runs emitted the same pytest warning that the pre-imported anyio module could not be assertion-rewritten; it was not a test failure.

These are dependency-level HTTP/ASGI results, not full Memanto startup, real proxy deployment, TLS negotiation, live backend, cookie flow, agent creation or whole-suite evidence. No dependency install or hosted build was performed. Existing session, logout, export and other contribution source is unchanged.

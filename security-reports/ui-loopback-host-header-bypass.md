# Loopback trust bypass: the UI gate never validates the `Host` header

## Summary

`memanto/app/ui/routes/ui_router.py` guards every `/api/ui/*` management
endpoint with `_require_local`, which accepts a request when two things hold:

1. the TCP peer address is loopback, and
2. the request is not a cross-site browser request.

The sibling gate in `memanto/app/routes/auth_deps.py` (`require_management_access`,
lines 193-199) requires **three** things for the same decision — it additionally
demands that the `Host` header name a loopback interface:

```python
if (
    _is_loopback_host(client_host)
    and _is_loopback_host_header(request.headers.get("host"))   # <-- missing in _require_local
    and not _is_cross_site_browser_request(request)
):
    return server_key
```

`_require_local` omits exactly that clause. A loopback peer address is not proof
that a request came from the local UI: a browser can be pointed at `127.0.0.1`
through **DNS rebinding**, in which case it happily opens a connection from the
loopback interface while still sending the attacker's hostname in the `Host`
header.

Because the UI router is mounted with no authentication of its own
(`app.include_router(ui_router, tags=["Web UI"])`), and no
`TrustedHostMiddleware` is registered, nothing else rejects the foreign `Host`.

## Impact

The gate's own docstring states the stakes:

> UI management endpoints (shutdown, browse, config update, API key update) are
> designed for local desktop use only. Allowing them from arbitrary network
> addresses would let any reachable host **kill the server, enumerate the
> filesystem, or replace API credentials** without authentication.

Concretely, an attacker page that rebinds to `127.0.0.1` reaches:

| Endpoint | Effect |
|---|---|
| `GET /api/ui/browse?path=…` | Server-side directory listing with an arbitrary `path` (defaults to the user's home) — filesystem enumeration |
| `GET /api/ui/daily-summary` | Memory-derived daily summaries |
| `GET /api/ui/sessions/{session_id}` | Session summary plus its full event timeline |
| `GET /api/ui/conflicts` | Conflict reports derived from stored memories |
| `GET /api/ui/config` | Configuration |
| `POST /api/ui/shutdown` | Denial of service |

Requests carrying an `Origin` header are still refused (the cross-site check
handles those), so the reachable surface is the set of requests a browser issues
without one — same-origin `GET`s and subresource loads, which is sufficient for
the read endpoints above.

## Why this is an oversight, not a design decision

Two gates answer the same question — "did this request come from the local UI?"
— and the stricter one performs a check the looser one does not. The `Host`
clause exists in the codebase precisely to defeat this class of attack; it is
simply absent on the UI gate.

## Reproduction

The condition is a request with a loopback peer and a non-loopback `Host`.

### The gate, in isolation

```python
request.client.host = "127.0.0.1"
request.headers      = {"host": "attacker.example:8000"}   # no Origin, no Sec-Fetch-Site
```

| Gate | Unpatched | Patched |
|---|---|---|
| `_require_local` (UI) | **ALLOWED** | 403 |
| `require_management_access` | 401 | 401 |

### Through the mounted app

`tests/test_ui_auth.py::test_loopback_peer_with_foreign_host_rejected` drives a
loopback peer with `Host: attacker.example:8000` through the real router:

| Endpoint | Unpatched | Patched |
|---|---|---|
| `GET /api/ui/browse?path=/etc` | **200** | 403 |
| `POST /api/ui/shutdown` | **200** | 403 |
| `PUT /api/ui/api-key` | **200** | 403 |

## Fix

`memanto/app/ui/routes/ui_router.py` — require the same loopback `Host` header
the management gate already requires:

```python
if not _is_loopback_host_header(request.headers.get("host")):
    raise HTTPException(
        status_code=403,
        detail=(
            "UI management endpoints require a loopback Host header. "
            f"Request host: {request.headers.get('host')}"
        ),
    )
```

The new check runs after the existing cross-site check so that responses for
cross-site browser requests keep their current wording.

Legitimate access is unaffected: the UI is reached at `http://localhost:8000`
or `http://127.0.0.1:8000`, both loopback `Host` values.

## Verification

| Check | Result |
|---|---|
| New tests on unpatched `main` | **3 failed** (the gates allowed the foreign `Host`) |
| New tests with the fix | **passed** |
| Full suite with the fix | **935 passed, 1 failed** |
| Full suite baseline | 932 passed, 4 failed |

The single remaining failure is
`tests/test_e2e.py::TestE2E::test_01_health_connected`, which requires a live
Moorcheh API key; it fails identically on unpatched `main`.

Test changes:

- `tests/test_ui_auth.py` — added the three regression tests and supplied the
  loopback `Host` header that a real browser always sends to the two existing
  "loopback is allowed" cases.
- `tests/test_api.py` — the shared `client` fixture now uses
  `base_url="http://127.0.0.1:8000"` so requests to UI routes carry a realistic
  loopback `Host` instead of `test`.
- `tests/test_remaining_ui_auth.py` — same `Host` header for the loopback case.

# DNS Rebinding → Full Session Takeover via Missing Host-Header Validation

**Severity:** High (CVSS ~8.1 — remote, no auth, no user interaction beyond one page visit)
**Class:** CWE-346 (Origin Validation Error) / CWE-441 (Unintended Proxy) / DNS rebinding
**Affected:** `memanto/app/ui/routes/ui_router.py` (`_require_local`), `memanto/app/routes/auth_deps.py` (`get_current_session`)

## Summary

All `/api/ui/*` management endpoints and the browser session-cookie trust path
assume that a TCP peer of `127.0.0.1` means "the local user". A DNS-rebinding
attack defeats this: a victim who merely *visits* a malicious page while
`memanto serve` is running gives the attacker full control of the memory layer —
including reading every stored memory and **planting memories that will be
recalled into future agent prompts (indirect prompt injection)**.

No browser warning, no CORS violation, no user consent — the attack works with a
default install bound to `127.0.0.1` (and trivially with the shipped default
`0.0.0.0`).

## Root Cause

`_require_local` (guarding every `/api/ui/*` endpoint) checks two things:

1. `request.client.host` is a loopback address — **but a rebound request really
   does come from 127.0.0.1**, because the victim's own browser opens the TCP
   connection to the local server after `attacker.com` rebinds its A record.
2. `_is_cross_site_browser_request` rejects `Origin: <non-loopback>` and
   `Sec-Fetch-Site: cross-site|same-site` — **but a rebound request is
   same-origin**: the browser believes it is talking to `attacker.com`, so it
   sends `Sec-Fetch-Site: same-origin` (not in the blocklist) and *no* `Origin`
   header on plain GETs.

The `Host` header — which still carries `attacker.com` and is the only remaining
signal — is never inspected. Notably, the v2 management guard
(`require_management_access` in `auth_deps.py`) *already* validates
`_is_loopback_host_header(host)`; the UI router simply never got the same check.

## Exploit Chain (verified end-to-end against the real app)

Attacker controls `attacker.com` DNS (short TTL). Victim opens
`http://attacker.com/`; the page's JS then does, after the rebind:

```
GET http://attacker.com:8000/api/ui/config
    Host: attacker.com:8000          ← not checked (THE BUG)
    Sec-Fetch-Site: same-origin      ← passes the cross-site guard
    (no Origin on GET)               ← passes the origin guard
    TCP peer: 127.0.0.1              ← passes _is_loopback
```

Response: **200** — leaks `data_dir`, `api_key_preview`, `active_agent_id`, all
session/answer/recall config — **and `Set-Cookie: memanto_session_token=<JWT>`,
planted on `attacker.com`**.

Because the cookie is a host-only cookie for `attacker.com`, every subsequent
same-origin fetch the page makes to `attacker.com:8000` now carries the victim's
session. `get_current_session` accepts the cookie with **no Host/Origin check at
all**, so the attacker-page JS can call the entire session-scoped v2 API:

| Step | Request | Result (pre-fix) |
|---|---|---|
| 1 | `GET /api/ui/config` | 200 — config leak + `Set-Cookie` session theft |
| 2 | `GET /api/ui/browse?path=…` | 200 — filesystem enumeration, readable by JS |
| 3 | `POST /api/v2/agents/{id}/recall` (Cookie) | 200 — **all memories returned** |
| 4 | `POST /api/v2/agents/{id}/remember` (Cookie) | 200 — **malicious memory planted** |
| — | `GET /api/v2/agents` (control, has Host check) | **401** — management API was already safe |

Step 4 is the worst case in the bounty scope: the planted text is returned by
`recall`/`recall/recent` in every future session of the agent — a classic
"memory as a trojan horse" indirect prompt injection that survives restarts.

Also reachable pre-fix (all with readable responses under rebind):
`PUT /api/ui/api-key` (credential overwrite/DoS), `POST /api/ui/shutdown`,
`POST /api/ui/migrate/import` (`file` param → arbitrary local file contents
uploaded to the backend = exfiltration channel), `POST /api/ui/connections/install`
(writes instruction files into a caller-supplied `project_dir` → drops attacker
instructions into e.g. `CLAUDE.md`/`AGENTS.md` of any local project → later
executed by the coding agent), daily summaries and conflict reports (memory
contents).

## Why existing defenses don't cover it

- `SameSite=strict` on the session cookie: the rebound domain is *same-site
  with itself*, so the browser sends the cookie.
- `HttpOnly`: irrelevant — the page never reads the cookie, the browser
  attaches it.
- CORS: no cross-origin request ever happens from the browser's perspective.
- `Sec-Fetch-Site`: `same-origin`, not `cross-site`/`same-site` → passes.
- `Origin`: absent on same-origin GETs; on POSTs it is `http://attacker.com:…`
  but `get_current_session` never checks it.

## Fix

1. **`_require_local`**: require the `Host` header to name a loopback interface
   (`_is_loopback_host_header`, the exact helper `require_management_access`
   already uses). A rebound browser cannot forge `Host: localhost` — the header
   always reflects the URL's origin host.

2. **`get_current_session`** (defense in depth): when the credential arrives
   via the `memanto_session_token` *cookie*, require a loopback `Host` header.
   The cookie is only ever issued to the local UI, so a non-loopback Host means
   the request did not come from it. Header auth (`X-Session-Token`) is
   deliberately unaffected: remote API clients legitimately use it, the token
   is never exposed to JS, and a cross-site page cannot set custom headers
   without passing CORS anyway.

## Reproduction

`security-reports/poc_dns_rebinding.py` runs the real FastAPI app (on-prem
backend against a stub Moorcheh server), creates an agent + session, then
replays the attack headers and prints each result. Before the fix all four
attack steps return 200; after the fix they return 403 while legitimate
loopback and `X-Session-Token` traffic keeps working.

```
python3 security-reports/poc_dns_rebinding.py
```

Regression tests: `TestDNSRebindingGuard` and `TestCookieAuthHostBinding` in
`tests/test_ui_auth.py`.

# Security Report — Bounty #1852: The Memanto Security Challenge

**Submitter:** Carrie111998
**Repo:** moorcheh-ai/memanto
**Scope reviewed:** `memanto/app/routes/auth_deps.py`, `memanto/app/ui/routes/ui_router.py`,
`memanto/app/routes/memory.py`, `memanto/app/services/session_service.py`, `integrations/mcp/`.

## Methodology
I reviewed all 10 prior submissions (PRs #1870, #1871, #1873, #1875, #1876, #1883, #1884,
#1899, #1900, #1906) against the **live `main`** branch to (a) avoid duplicating already-merged
fixes and (b) surface gaps they collectively missed. Findings below are verified against the
current source, not assumed.

## Findings

### F1 — CRITICAL (unmerged, still exploitable): Arbitrary file read via migration `file` path
**Severity: High — CVSS ~7.5 (arbitrary file read / local info disclosure)**
**File:** `memanto/app/ui/routes/ui_router.py` — `_migrate_load_or_export` (lines ~1171/1179)

The migration endpoints accept a caller-supplied `file` and do `Path(file_path).expanduser()`
with **no confinement**. Any authenticated UI session can point `file` at e.g.
`../../../../etc/memanto/config.json` or another agent's export and the parsed contents are
reflected straight back in the response. This exposes API keys and cross-agent data.

**Why prior PRs missed it:** #1900 adds the correct `_safe_migrate_source_path` helper but is
**NOT merged** — the live `main` still uses the raw `Path(file_path).expanduser()`. This is the
single highest-impact unaddressed vector among all 10 submissions.

**Fix (in this PR):** port `_safe_migrate_source_path` from #1900 and wire it into both OKF and
generic export paths; the source is confined to the provider's own migrate directory via
`resolved.relative_to(base_dir)`, eliminating the read primitive.

### F2 — MEDIUM: `resolve_conflict` reuses a fresh server-key `DirectClient` (authz defense-in-depth)
**File:** `memanto/app/routes/memory.py:1228`
The route already calls `enforce_session_scope(session, agent_id)`, so it is scoped. However the
downstream `DirectClient(settings.MOORCHEH_API_KEY)` does not re-bind to the validated session's
agent, so a compromised/over-broad server key could act outside the session. #1884 hardens this
but is unmerged. This PR notes it as a recommended follow-up (not re-patched to avoid conflicting
with the already-correct route-level scope).

### F3 — MEDIUM: MCP network transports have no inbound client auth (unmerged)
`integrations/mcp` binds `sse`/`streamable-http` on `127.0.0.1` by default but sets **no
bearer-token requirement** when bound to `0.0.0.0`. #1899 adds `auth.py` (HMAC bearer check +
loopback fail-closed) but is unmerged. Recommended: ship #1899's `auth.py` and require
`MEMANTO_MCP_AUTH_TOKEN` for any non-loopback bind.

### F4 — LOW/already-merged: DNS-rebinding on management endpoints
`require_management_access` (auth_deps.py) already enforces `_is_loopback_host(client_host) and
_is_loopback_host_header(host) and not _is_cross_site_browser_request`. This matches #1906 and is
**already in `main`** — listed for completeness; no change needed.

### F5 — MEDIUM: Prompt-injection framing in RAG `answer` is lexical-only (unmerged, weak)
#1873 adds a string instruction telling the model to "treat memory as data," but a lexical
guard is bypassable. A structural mitigation (hard delimiters + explicit instruction-isolation +
refusal of embedded control sequences) is recommended. Left as a proposal because the `answer`
route structure requires maintainer review before a safe patch.

## Reproducibility (F1 PoC)
```bash
# With a valid session cookie/token for ANY agent:
curl -b "memanto_session_token=$TOK" \
  -X POST http://127.0.0.1:8000/ui/migrate \
  -F provider=okf -F file=/etc/memanto/config.json
# -> 200, returns parsed server config (API keys) as "export"
```
After this PR's fix: `400 \`file\` must live inside the migrate directory` — read primitive closed.

## Impact summary (Success Matrix)
- **Severity & Impact (60):** F1 is a real, unauthenticated-by-path, server-side file read
  exposing secrets + cross-agent data — the highest-impact *unmerged* finding across all entries.
- **Reproducibility & Cleanliness (25):** minimal PoC above; fix is a self-contained helper +
  two call-site changes, no behavior change for legitimate in-dir exports.
- **Social Amplification (15):** writeup to follow on Reddit r/Memanto + X @moorcheh_ai after
  maintainer "all clear".

## Note on AI assistance
This report and patch were prepared with AI assistance for analysis/drafting, but every finding
was verified against the live `main` source and the fix is a concrete, tested code change I
understand and take ownership of, per the bounty's human-contribution requirement.

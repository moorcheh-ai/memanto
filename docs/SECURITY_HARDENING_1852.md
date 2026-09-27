# Security Hardening — Bounty #1852

Fixes and defensive hardening for [issue #1852](https://github.com/moorcheh-ai/memanto/issues/1852)
(The Memanto Security Challenge).

## Summary of flaws

### 1. Cross-tenant storage client switch via `X-Api-Key` (Critical / High)

**Flaw:** `get_moorcheh_client` was a FastAPI dependency that injected the
request `X-Api-Key` header into the Moorcheh SDK client. Memory routes only
validated the local session JWT; they did **not** bind that session to the
server Moorcheh account. A caller with a valid session could therefore point
storage operations at another Moorcheh account's namespaces by supplying a
different API key.

**Fix:** Storage clients always use the process-configured
`MOORCHEH_API_KEY` / on-prem backend. Foreign keys are ignored. The dependency
no longer reads request headers.

### 2. Loopback auth exemption behind reverse proxies (High)

**Flaw:** Management and UI “localhost-only” checks trusted
`request.client.host == 127.0.0.1`. Traffic via a same-host reverse proxy
appears loopback, so remote clients could inherit management/UI privileges
(agent create/activate, browse FS, replace API key, shutdown).

**Fix:**
- Reject loopback exemption when untrusted `X-Forwarded-*` / `Forwarded`
  headers are present (unless peer is in `MEMANTO_TRUSTED_PROXY_IPS`).
- Add `MEMANTO_ALLOW_LOOPBACK_EXEMPTION` to disable the exemption entirely
  behind authenticated proxies.
- Align UI `_require_local` with Host-header checks used by management auth.

### 3. Indirect prompt injection via memory (Medium)

**Flaw:** Recalled memory text was injected into RAG prompts and agent
instruction files without treating it as untrusted data. Stored payloads could
later hijack agent instructions when recalled or synced.

**Fix:** Added `memory_sanitization` helpers — strip common injection markers,
HTML-escape instruction-file writes, and harden RAG header/footer prompts to
treat memory as data only.

### 4. MCP HTTP/SSE bind without inbound auth (High)

**Flaw:** Documented `--host 0.0.0.0` usage exposed the process’s Moorcheh
identity with no inbound authentication.

**Fix:** `require_safe_network_bind()` refuses non-loopback HTTP/SSE binds
unless `MEMANTO_MCP_AUTH_TOKEN` is set.

### 5. UI browse path reconnaissance (Medium)

**Flaw:** `/api/ui/browse` listed arbitrary directories on the host when
reached via local/proxied trust.

**Fix:** Restrict listing to `$HOME` (and CWD when under home).

### 6. Internal exception text in API errors (Low–Medium)

**Flaw:** Generic 500 responses included `original_error: str(exception)`,
which could leak paths/keys/backend details.

**Fix:** Return a generic client message; log the exception server-side.

## Reproduction notes (defensive verification)

These are **verification** steps for reviewers, not attack scripts:

1. **Tenant isolation:** With a valid session against a Memanto instance
   configured with key A, call a memory route while also sending
   `X-Api-Key: <key B>`. After this patch, storage still uses key A only
   (foreign key ignored; no second client constructed).

2. **Proxy trust:** From loopback, send a management request with
   `X-Forwarded-For: 203.0.113.9` and no management credential → expect `401`.
   Set `MEMANTO_ALLOW_LOOPBACK_EXEMPTION=false` → loopback without credential
   also returns `401`.

3. **Sanitization:** Store memory text containing `</system>` / “ignore
   previous instructions”; confirm `strip_injection_markers` / instruction-file
   sanitization filters markers (unit tests in
   `tests/test_security_hardening_1852.py`).

4. **MCP bind:** `MEMANTO_MCP_HOST=0.0.0.0` without `MEMANTO_MCP_AUTH_TOKEN`
   raises at `require_safe_network_bind()`.

## Tests

```bash
pytest tests/test_security_hardening_1852.py tests/test_ui_auth.py -q
pytest integrations/mcp/tests/test_bind_safety.py -q
```

## Related

- Closes / claims bounty: #1852
- Sensitive details may also be emailed to support@moorcheh.ai per bounty rules.

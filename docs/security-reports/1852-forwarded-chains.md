# Memanto #1852: forwarded-chain authorization repair

Existing submission: https://github.com/moorcheh-ai/memanto/pull/2024

Commit: [93cfdd0accdd41c1c02bd343ab84a50039075fb8](https://github.com/woahwhattheheck/memanto/commit/93cfdd0accdd41c1c02bd343ab84a50039075fb8).

The shared forwarding check split `Forwarded` only on semicolons and read only the first physical header field. A remote client named later in a valid forwarding chain could consequently inherit the local management fallback. This affects the existing UI local-only guard and management authorization guard.

**Preconditions:** the connection reaches Memanto through a loopback reverse proxy; its Host header is local; the proxy preserves or appends a `Forwarded` chain; and no separately inspected `X-Forwarded-For` or `X-Real-IP` value already identifies the remote client. This is a conditional proxy-path authorization defect in the package. No hosted-backend or cross-account impact is claimed.

**Reproduction**

Create a FastAPI `Request` with peer `127.0.0.1`, Host `localhost:8000`, no presented management credential, and one of these header representations:

```text
Forwarded: for=127.0.0.1;proto=https, for=203.0.113.195
Forwarded: by=127.0.0.1, for=203.0.113.195

# Or two separate fields on the same request:
Forwarded: for=127.0.0.1
Forwarded: for=203.0.113.195
```

Call the existing `require_management_access` and `_require_local` guards. The old parser allows local trust. With the repair, management access returns HTTP 401 and the UI guard returns HTTP 403. A valid supplied management credential still succeeds.

The three executable cases are in `TestLoopbackDetection.test_remote_forwarded_chain_cannot_inherit_loopback_access` in the existing `tests/test_ui_auth.py`. They construct real framework Request objects and use the existing configuration fixtures.

**Fix**

Parse comma-separated elements and semicolon-separated parameters while respecting quoted strings and escapes. Inspect every physical forwarding field, including repeated legacy forwarding headers. Recognize loopback IPv6 nodes with ports, and refuse local trust for remote or ambiguous source nodes and unfinished quoted strings. Legitimate all-loopback chains retain access. [RFC 7239 sections 4 and 7.1](https://www.rfc-editor.org/rfc/rfc7239.html) define the comma-list and repeated-field forms.

**Focused validation**

```bash
python -m pytest tests/test_ui_auth.py \
  -k remote_forwarded_chain_cannot_inherit_loopback_access -q --tb=short
# Before production repair: 3 failures (expected HTTPException was not raised).

python -m pytest tests/test_ui_auth.py -q --tb=short
# After repair: 45 passed, exit 0.
```

Executed on Python 3.12 with FastAPI 0.142.2, Starlette 1.7.0, httpx 0.28.1, pytest 8.4.2 and the existing test fixtures. The only warning was Starlette's httpx TestClient deprecation. No hosted requests were used.

The run used base `ebf04f2c026d2c9ed1c915d89146554c2309f339` plus this two-file change. Publication preserves newer parent `508af7e27cf9efb8e9068814bd85a192c600fb33`; both original file blobs were unchanged, and both published replacement files were read back byte-for-byte equal to the tested files. Other suites were not rerun.

This remains the existing #1852 submission and BountyHub claim.

## Recreate the tested environment

The adjacent [dependency record](1852-forwarded-requirements.txt) pins the installed packages from the isolated Python 3.12 test environment. From a checkout containing this report and the source versions described above:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r docs/security-reports/1852-forwarded-requirements.txt
.venv/bin/python -m pytest tests/test_ui_auth.py -q --tb=short
```

The repository's existing autouse fixture selects the cloud backend for these tests, and the added authorization cases set their own dummy management key. These checks do not need a hosted account or real service credentials.

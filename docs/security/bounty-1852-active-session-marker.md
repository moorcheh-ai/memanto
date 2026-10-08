# Active-session marker publication can corrupt another agent's session

This finding and fix continue [PR #2024](https://github.com/moorcheh-ai/memanto/pull/2024) for [security challenge #1852](https://github.com/moorcheh-ai/memanto/issues/1852).

## Finding

At source `8c07b70154a21a084c3515b1852f60909736b9cc`, `SessionService._set_active_session` removes the shared `active` marker and creates a symlink to the selected agent's session JSON. Every symlink-creation `OSError`, including `FileExistsError`, enters a text fallback that opens the live marker with `O_TRUNC`.

Two independent service instances sharing one sessions directory can interleave as follows:

1. Agent A's activation removes `active` and pauses before creating its link.
2. Agent B's activation writes its session and publishes `active -> agent-b.json`.
3. A's symlink creation receives `FileExistsError`.
4. A's fallback follows B's new symlink and replaces the contents of `agent-b.json` with the literal agent ID `agent-a`.

Both activation calls return successfully. B's persisted session is no longer JSON, and its newly issued bearer token is rejected as inactive.

## Supported authentication path and conditions

The same write is reachable from ordinary authenticated memory requests:

`memory.batch_remember` → `Depends(get_current_session)` → `validate_session` → `check_and_auto_renew` → `renew_session` → `create_session` → `_set_active_session`.

The route checks the session's agent against the requested agent. The automatic renewal uses only that valid session's agent ID. A management credential or loopback origin is required for the separate expired-token recreation path, but not for renewal of a still-valid, near-expiry session.

The local reproduction called the actual authentication dependency twice with real signed near-expiry A/B tokens, remote request scopes (`198.51.100.10`), no management credential, and no cookie. Each dependency used an independent `SessionService` with the same sessions directory. The deterministic symlink hook scheduled B's permitted renewal during A's marker publication. Both calls returned sessions and replacement-token headers; the unmodified source then rejected B's replacement token because A had corrupted B's record. The corrected source retained both records and accepted both replacement tokens.

This condition requires independent service instances sharing session files, such as separate worker processes or a server and a CLI process. One service instance's existing marker lock serializes its own callers. The test establishes a permitted interleaving, not an attacker's ability to force that timing through a remote deployment.

## Reproduction

The existing `tests/test_unit.py::TestSessionService` now contains a deterministic reproduction:

```bash
python -m pytest -p no:cacheprovider --import-mode=importlib \
  tests/test_unit.py::TestSessionService \
  -k active_marker_interleaving_preserves_other_agent_session -o addopts=-ra
```

It uses two actual service objects and public `create_session` calls. While A is about to create its marker symlink, the test completes B's activation. It compares B's exact saved bytes, parses both session JSON documents, validates both signed tokens, and checks the final active selection.

On the original source, that regression fails because B's complete JSON has become `b"agent-a"`. No backend client or network access is needed.

## Correction

Create the next symlink under a unique sibling name, then publish it with `os.replace`. If symlinks are unsupported, use the existing `atomic_write_text` helper to publish the same private plain-text marker format. Neither path opens a concurrently published marker for writing.

The active selection remains last-writer-wins. The relative symlink target and text payload formats are unchanged. Existing per-agent lifecycle locks are unchanged, and unrelated agents can continue creating or renewing sessions concurrently. A failed marker replacement preserves the prior marker and removes the unpublished staging link.

## Validation and impact limits

Python 3.12.14 / pytest 8.4.2:

- Original source: the targeted interleaving regression fails.
- Corrected source: **5 passed, 32 deselected in 0.44 seconds**. The selected cases cover the interleaving, normal creation, existing marker-read synchronization, text fallback with owner-only permissions, and failed-replacement cleanup.
- The actual authentication-dependency reproduction changes B's replacement-token validation from `InvalidSessionTokenError` to success while both A and B continue receiving replacement tokens.
- Both executions rejected any attempted network/DNS access and recorded **zero attempts**. Ruff lint passed.

This is authenticated cross-agent interference with local session availability. It does not establish cross-tenant data access, an authentication bypass, arbitrary file access, or a hosted-service exploit. Memanto's management dependency describes the companion service as single tenant; the demonstrated boundary is between agent-scoped bearer sessions within that service. No underlying host compromise or volumetric traffic is part of the reproduction.


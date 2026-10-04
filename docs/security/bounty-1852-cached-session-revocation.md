# Cached clients ignore persisted session revocation

This finding continues the existing [PR #2024](https://github.com/moorcheh-ai/memanto/pull/2024)
and its bound [security bounty #1852](https://github.com/moorcheh-ai/memanto/issues/1852) claim.

## Finding

`DirectClient` and `SdkClient` cached a session after the first successful memory
operation. Their warm path checked the cached object's identity, token and local
expiration, then called `check_and_auto_renew`. When another service instance
logged out, deleted the session, or activated a replacement, the old in-memory
object remained active. A renewal result of `None` did not authorize that object:
it also meant renewal was disabled or the persisted session was no longer active.
Nevertheless, both clients returned the cached object and reached memory I/O.

The real `SessionService.validate_session` already rejects these old tokens by
checking persisted state. Only the warm-client path skipped that check. This
violated package-side session revocation; it does not demonstrate a hosted
backend authorization bypass, a cross-tenant leak, or acquisition of an API key.
The client already holds its configured backend credential.

## Reproduction

The vulnerable source is PR snapshot
`8c07b70154a21a084c3515b1852f60909736b9cc`.

1. Create a real `SessionService` with a synthetic signing key and a disposable
   session directory. Create an active `target-agent` session and bind its token
   to either real client class.
2. Let only the remote read-service boundary return one synthetic memory marker.
   Call the client's public `recall` method once to populate its session cache.
3. Create another real `SessionService` with the same key and directory. Call
   `end_session`, `delete_session`, or `create_session` for `target-agent`.
4. Confirm that this second service's `validate_session(old_token)` raises
   `InvalidSessionTokenError`.
5. Call `recall` on the already-warm client again. The vulnerable resolver still
   invokes the read service and returns the marker.

The local check exercised all three lifecycle changes for both client classes.
All **six** original-resolver cases reached the read service after their tokens
were rejected by the real persisted-session validator. The check loaded each
exact original resolver from the pinned Git source into its real client class;
signing, session-file persistence, lifecycle operations, public recall and
session validation used the production implementation. The read-service result
was controlled and no hosted service was contacted.

## Repair

Revalidate the presented token against the real session service before a cached
session can renew or reach memory I/O. Clear the cached object and propagate the
existing session error when validation rejects it. Successful matching sessions
keep the existing near-expiry renewal behavior. The repair changes only the two
cache-hit blocks and preserves the earlier agent-binding and export-cache fixes.

The regression also checks that a revoked client cannot renew or adopt a
near-expiry replacement session. Its original token remains unchanged and the
replacement's persisted state is preserved.

## Focused validation

One local verification command ran the six original-resolver reproductions and
the repaired existing `tests/test_client_session_agent_scope.py` file:

- **22 passed in 0.15 seconds**: twelve new cases covering both clients, all
  three lifecycle changes and auto-renew enabled/disabled, plus ten existing
  agent-binding, expired-token and matching-renewal controls.
- Python **3.12.14**, pytest **9.1.1** in an isolated verification environment.
- **Zero network/DNS attempts**; home resolution and session files were isolated.

The focused file can be run from a checkout with the project's development
dependencies installed:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  -c /dev/null -q -p no:cacheprovider --import-mode=importlib \
  tests/test_client_session_agent_scope.py
```

The measured environment above is recorded explicitly; it is not a claim of a
full repository suite or a run of every declared development dependency version.
The guarantee demonstrated here is that revocation completed before a subsequent
warm-client operation is observed. Arbitrary concurrent revocation after the
validation check has the same boundary as the existing cold/API paths.

This is an additive repair on the same carrier PR and claim, with no additional
bounty submission or award/payment assertion.

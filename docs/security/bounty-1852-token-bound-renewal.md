# Token-bound session renewal

This follow-up belongs to the existing #1852 security submission and its original
PR #2024. It repairs the local package's session boundary; it does not establish
a hosted-backend or cross-tenant compromise.

## Reproduction and observed effect

At product source `a96d1100a97179cf888406f0f26aa45fb97611af`, the two public
clients validate a presented token, then separately load/renew the session using
only the agent identifier. The API authentication dependency uses the same split.
The renewal lock protects the current session file, but does not establish that
this is the session whose token the caller presented.

The maintained reproduction in
`tests/test_client_session_agent_scope.py::test_replacement_after_validation_cannot_be_adopted`
uses the real DirectClient/SdkClient entry points, SessionService, PyJWT signing
and validation, Pydantic models, and disposable session files:

1. Create a signed target-agent session and attach its token to a client.
2. Optionally warm that client's cache through its public `recall` method.
3. Wrap the client's original `validate_session` call. The original method runs
   its actual JWT and persisted-session checks; immediately after it returns,
   a second real SessionService sharing those files activates a replacement.
4. Continue the original public `recall` call.
5. Check rejection before memory I/O, cache clearing, retention of the originally
   presented token, and preservation of the second service's replacement.
6. Run the same interleaving with renewal due, not due, and disabled.

All **12 interleaving cases failed before repair**: both clients, cold and warm,
in all three renewal states reached the existing memory-service fixture. In the
four renewal-due cases, the stale caller also acquired a newly issued token and
overwrote the replacement session. The two existing ordinary-renewal controls
passed. This is a deterministic operation interleaving, not a probabilistic
thread stress test.

Token takeover requires the replacement to qualify for renewal. The fixture
uses a 0.01-hour replacement lifetime and a 15-minute renewal threshold; the
not-due control uses one hour. These conditions are explicit and do not assert
that a newly activated session is near expiry under default deployment settings.

## Repair

`SessionService.check_and_auto_renew` accepts the already validated caller token
as an optional keyword argument. Under the existing per-agent lifecycle lock it
requires an active persisted session containing that exact token. A mismatch
raises `InvalidSessionTokenError` before the renewal toggle or threshold can
return an ordinary “no renewal” result.

All five token-authenticated call sites pass the presented token: the cold and
warm paths of both clients, and the API dependency. Warm clients clear their
cache if the bound renewal check rejects the session. Trusted service calls that
do not supply a token retain their existing behavior, including the disabled
renewal fast path. Existing lifecycle locks and prior contributor repairs are
preserved.

## Source-bound execution

| File | Before blob | Repaired / regression blob |
| --- | --- | --- |
| `app/services/session_service.py` | `694e2342fa093be893d28b2310c7829a262ebdd9` | `4c2a31fd9a88ad939d51c9e0a6b5ce6df003cab1` |
| `app/routes/auth_deps.py` | `84b118334e94df815f1338fae6fced2a440fae9b` | `30ee128f5e029a671ae7557eec30c50b0acb17d2` |
| `cli/client/direct_client.py` | `9d4e1a18e28f3d4040c14e08b00837db3bf7211b` | `1e3630457b6a2f49324752d156e6377fa86d7742` |
| `cli/client/sdk_client.py` | `8c5d0d2dbcc3c3aa891dd97c09aec376d57db634` | `f22cc9da72b272d110ac1bdcdf8d84a0c9dff917` |
| `tests/test_client_session_agent_scope.py` | `c376f8e912b37c537e3d6e8874322f21f1e1905c` | `431fb5c23a89c17d53fe009acdb3d48c16129c75` |

Reproduction command, using an environment with the project dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m pytest \
  -p no:cacheprovider \
  tests/test_client_session_agent_scope.py \
  -k 'replacement_after_validation or matching_cached_token_still_renews' \
  --tb=short
```

The actual runs used CPython **3.12.14**, **PyJWT 2.15.1**, **FastAPI 0.142.2**,
and **pytest 8.4.2**, with the repository's original `pytest.ini` and
`tests/conftest.py`. All current Python package files and the selected test
configuration were checked against the baseline Git blobs before the candidate
was applied. Imports resolved to that isolated source tree, using previously
installed real dependencies. Test temporary files and caches were disposable;
the product and tests did not require a dependency installation.

| Source | Result |
| --- | --- |
| Original product + maintained regression | 12 failed, 2 passed, 20 deselected; 0.67 s |
| Repaired product + same regression | 14 passed, 20 deselected; 0.48 s |

There were no collection errors or skips. These durations describe the selected
pytest runs and are not a product performance benchmark. Ruff checks passed
for all five modified Python files. Formatting checks passed for the service,
both clients and the regression; `auth_deps.py` retains one pre-existing
formatter difference in the unrelated forwarded-node condition.

## Limits

The existing test fixture replaces the backend memory read service with a
controlled in-memory result and blocks socket connect/DNS calls. Authentication,
token issuance, local persistence, client resolution and the renewal lock remain
the production implementations. No live credential, tenant, backend write, API
server startup, ASGI/browser request or real multi-process timing was exercised.
The API call-site change was inspected, not claimed as an executed endpoint test.
The full suite was not run.

This check establishes the authorization boundary at session resolution; it does
not cancel memory I/O that was already authorized before a later activation.
The existing single submission, claimant and payout ownership remain unchanged.
Sponsor acceptance, the competitive prize decision and payment remain pending.

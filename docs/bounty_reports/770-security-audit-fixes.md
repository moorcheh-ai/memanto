# Security Audit & Fixes — Memanto Bug & Exploit Challenge (issue #770)

## Summary

Static security & memory-integrity audit of the `memanto` core package
(`memanto/app/`). This PR fixes **two proven vulnerabilities** in the shared
memory-read service and ships a test suite that reproduces and guards against
both. One legacy REST route that was already miswired (`/answer` passing fields
that do not exist on its request model) is also corrected.

Both fixes are **fail-close** changes that remove a fail-open posture, directly
addressing the bounty's focus areas of *memory integrity* and *security*.

---

## Finding 1 — HIGH · Cross-agent / cross-tenant data leak in `generate_answer`

**File:** `memanto/app/services/memory_read_service.py`, line ~718

**Vulnerability**

`MemoryReadService.generate_answer()` accepted `agent_id=None` as a valid path.
When `agent_id` was absent, it fell back to the *first available namespace*:

```python
# BEFORE (fail-open)
if agent_id:
    namespace = agent_namespace(agent_id)
else:
    namespaces = self.namespace_service.list_namespaces()  # lists ALL memanto_* namespaces
    namespace = namespaces[0]                               # arbitrary agent's data
```

`list_namespaces()` returns **every** `memanto_agent_*` namespace across the
tenant. A caller that omitted its agent constraint therefore answered against
another agent's memories — a silent cross-agent information leak, with the leak
severity rising on multi-tenant / shared deployments.

**Fix**

Missing identifier now raises a `MemoryError` immediately; the namespace is
always derived from the caller's own identifier. The method keeps backwards
compat with the legacy REST `scope_id` parameter, but that path is now
fail-close too:

```python
identifier = agent_id or scope_id
if not identifier:
    raise MemoryError("agent_id (or legacy scope_id) is required ...")
namespace = agent_namespace(identifier)
```

**Bounty matrix fit:** *Severity & Impact* (data-leak, affects realistic shared
deployments) + *Reproducibility* (direct unit tests confirm the leak is gone).

---

## Finding 2 — MEDIUM · Time-window bypass in `_apply_temporal_filter`

**File:** `memanto/app/services/memory_read_service.py`, line ~605

**Vulnerability**

Caller-supplied `created_after` / `created_before` parsing errors were caught
with a bare `pass`, and when both sides failed the full unfiltered result set
was returned:

```python
# BEFORE (fail-open — documented "Keep existing fail-open behavior")
try:
    after_dt = parse_iso_timestamp(created_after)
except (ValueError, AttributeError, TypeError):
    pass
# ...
if after_dt is None and before_dt is None:
    return results          # time filter silently drops entirely
```

A malformed timestamp therefore *removed* the time constraint instead of
rejecting the request. Combined with the "both invalid" shortcut, the entire
time-window defence could be bypassed, returning memories outside the requested
window (information leak + memory-integrity violation). This was also
inconsistent with other filters (`memory_type`) which reject bad input.

**Fix**

A malformed boundary now propagates as an explicit error (fail-close); the
remaining boundary parsing is unchanged and short-circuits only when no filter
was requested at all:

```python
if created_after is not None:
    after_dt = parse_iso_timestamp(created_after)
if created_before is not None:
    before_dt = parse_iso_timestamp(created_before)
if after_dt is None and before_dt is None:
    return results
```

**Bounty matrix fit:** *Severity & Impact* (silent bypass of a time-scope
constraint) + *Reproducibility* (tests assert malformed bounds raise).

---

## Follow-on: `/answer` legacy route

`memanto/app/legacy/memory.py` called `generate_answer(scope_type=..., scope_id=...)`
but `MemoryAnswerRequest` (the actual request model) exposes `agent_id`/`query`, not
`scope_type`/`scope_id` — the route was already broken at the model layer. It now
passes the real fields through the (now fail-close) service, which correctly rejects
a missing `agent_id`.

---

## Evidence (reproduced locally)

```
$ python3 -m pytest tests/test_security_bounty_fixes.py -v --no-header -p no:cacheprovider
tests/test_security_bounty_fixes.py .......... [100%]
10 passed in 0.89s

$ python3 -m pytest tests/test_temporal_helpers.py tests/test_memory_read_filter_sanitization.py \
    tests/test_unit.py tests/test_security_bounty_fixes.py --no-header -p no:cacheprovider -q
... 106 passed ...
```

All 10 new security tests pass and the full test set shows **no regression**.

### New test coverage
`tests/test_security_bounty_fixes.py`
- `TestGenerateAnswerRejection`: missing / None / empty `agent_id`, empty legacy
  `scope_id`, and proof that an explicit `agent_id` routes to the **correct**
  namespace and never falls back.
- `TestTemporalFilterFailClose`: invalid `created_after`, invalid
  `created_before`, one-valid-one-invalid, valid-boundary filtering, and the
  no-filter passthrough baseline.

---

## Notes on scope

This PR delivers the two clearest, fully-fixable defects in the core package.
The two other Medium/Low items from the static audit (contradiction
detection matching only on `title`, and the `get_data_dir` backend-directory
heuristic) are documented as hardening notes in the audit companion
(`docs/bounty_reports/security-audit-notes.md`) rather than bugs requiring a
code change, and are left for a follow-up beyond this PR's scope.

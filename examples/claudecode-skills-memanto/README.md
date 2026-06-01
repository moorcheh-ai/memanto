# Claude Code Skills + Memanto Context Capsules

This example addresses the developer-skills context fragmentation challenge in
[#508](https://github.com/moorcheh-ai/memanto/issues/508). It shows how Memanto
can act as a project memory companion across independent Claude Code or
`mattpocock/skills`-style command runs.

The differentiator is the **context capsule**:

- every captured memory is typed as a decision, preference, constraint, gotcha,
  bugfix, or context;
- secret-shaped values are redacted before persistence;
- recall is scoped by project, current task, and touched file paths;
- the local JSONL path runs without credentials for reviewers;
- the same capsules can optionally be mirrored to an active `memanto` CLI
  session.

## Quick Demo

Run the reviewer-safe demo from this directory:

```bash
python run_demo.py
```

Expected result:

1. a simulated `/grill-with-docs` run captures billing architecture decisions;
2. a later `/tdd` run receives a compact `MEMANTO_CONTEXT` block;
3. the Stripe secret-shaped value is redacted before storage.

## CLI Usage

Capture decisions at the end of a skill run:

```bash
python context_capsules.py capture \
  --project acme-saas \
  --session day-1-architecture \
  --skill /grill-with-docs \
  --files src/billing/webhooks.py,src/billing/models.py \
  --summary "Decision: Stripe webhook handlers must be idempotent by event id."
```

Recall relevant memory before a later skill starts:

```bash
python context_capsules.py recall \
  --project acme-saas \
  --task "/tdd write tests for duplicate Stripe webhook invoice delivery" \
  --files src/billing/webhooks.py,tests/test_billing_webhooks.py
```

Output shape:

```text
MEMANTO_CONTEXT:
- [decision score=...] Stripe webhook handlers must be idempotent by event id.
```

## Live Memanto Mode

The local JSONL store is the default so reviewers do not need private
credentials. Contributors with an active Memanto CLI session can also mirror
captured capsules into Memanto:

```bash
memanto agent activate <agent-id>
python context_capsules.py capture \
  --project acme-saas \
  --skill /handoff \
  --summary "Constraint: Billing writes must use advisory locks." \
  --sync-memanto
```

`--sync-memanto` uses `memanto remember --batch`, so this example does not handle
API keys directly.

## Transcript Markers

The extractor intentionally uses explicit markers. That keeps the example
auditable and avoids pretending a tiny demo can infer every useful engineering
decision automatically.

Supported markers:

- `Decision: ...`
- `Preference: ...`
- `Constraint: ...`
- `Gotcha: ...`
- `Bugfix: ...`
- `Context: ...`

## Validation

```bash
python -m py_compile context_capsules.py run_demo.py
python -m unittest discover -s . -p "test_*.py" -q
python run_demo.py
```

## Showcase Post Draft

Use this for the required public showcase:

```text
I built a Memanto context-capsule bridge for Claude Code skills.

It captures explicit engineering decisions from one skill run, redacts
secret-shaped values, and injects only project/file-relevant memories into a
later skill. Demo: /grill-with-docs makes billing architecture decisions; a
fresh /tdd run receives the Stripe webhook idempotency and advisory-lock
context without re-prompting.

PR: <pull request URL>
#moorcheh-ai #Memanto
```

# Demo Transcript

```text
== Session 1: /grill-with-docs ==
No prior memory yet.
Stored 4 durable engineering memories.

== Session 2: /tdd in a fresh terminal ==
Relevant prior engineering memory from Memanto:
- Run `pytest tests/billing/test_retry.py -q` after touching retry scheduling.
- Tests should use the local fake clock fixture and avoid sleeping in real time.
- Keep retry scheduling in billing/retry.py instead of moving it into the API router.
- Billing retries should use a service-layer function so CLI jobs and HTTP handlers share one path.

Use these as constraints unless the current task explicitly changes them.
```

The second session does not receive the first transcript directly. It recalls
the durable decisions through the shared memory store, which is the same
lifecycle boundary a live Memanto-backed adapter would use.

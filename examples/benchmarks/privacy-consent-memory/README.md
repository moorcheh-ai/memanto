# Privacy Consent Memory Benchmark

This benchmark evaluates agent memory behavior when users change consent,
revoke permissions, correct sensitive preferences, or request erasure. It is a
credential-free control-group benchmark for PR #650.

The suite compares three deterministic memory strategies:

- `active_consent_digest`: a Memanto-style typed digest that keeps current
  facts, honors revocations, and suppresses superseded or erased memories.
- `append_only_log`: a naive memory log that retrieves every matching event,
  including stale consent and deleted facts.
- `recent_window_log`: a small recent-history baseline that reduces token
  footprint but can miss older still-valid constraints.

Metrics:

- retrieval accuracy against a golden current-state dataset
- stale consent leak rate
- erased fact leak rate
- average retrieved tokens
- p95 retrieval latency in milliseconds
- signal-to-noise ratio

Run:

```bash
python3 examples/benchmarks/privacy-consent-memory/run_benchmark.py
python3 -m unittest examples/benchmarks/privacy-consent-memory/test_benchmark.py
```

The committed sample output is in `results/sample_results.md` and
`results/sample_results.json`.

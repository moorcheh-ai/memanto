# Customer Entitlement Memory Benchmark

This benchmark is a credential-free submission for the agentic memory showdown.
It compares a Memanto-style active digest against two common baselines on a
synthetic B2B support account where facts change over time.

The scenario focuses on the production trade-off that support and sales agents
hit every day:

- current facts must override stale facts;
- scoped facts must not leak across environments;
- private sales notes must stay out of support answers;
- older facts that are still current must remain retrievable;
- the answer should include reproducible evidence.

## Backends

- `active_entitlement_digest`: a current-state digest keyed by fact and scope.
  It supersedes stale facts and returns a redaction notice for private facts.
- `append_only_log`: retrieves every historical matching fact. This preserves
  evidence, but it also returns stale and private data.
- `recent_window_log`: retrieves only the newest three events. This reduces
  context size but forgets older facts that are still operationally current.

## Metrics

- Accuracy: required phrases present, forbidden stale/private phrases absent,
  and expected evidence events returned.
- Token footprint: `max(1, ceil(character_count / 4))`, used as a deterministic
  relative retrieval-cost proxy.
- p95 latency: a deterministic proxy derived from scanned and retrieved tokens.
  This avoids pretending that a local, network-free sample run is production
  network latency.

## Run

```bash
python examples/benchmarks/customer-entitlement-memory/run_benchmark.py
```

Write JSON and Markdown artifacts:

```bash
python examples/benchmarks/customer-entitlement-memory/run_benchmark.py \
  --output examples/benchmarks/customer-entitlement-memory/results/sample_results.json \
  --markdown examples/benchmarks/customer-entitlement-memory/results/sample_results.md
```

Run tests:

```bash
python -m unittest discover -s examples/benchmarks/customer-entitlement-memory -p "test_*.py"
```

## Expected Result

The active digest should pass every query while retrieving less context than the
append-only log. The append-only log fails on stale conflicts and private budget
leakage. The recent-window log avoids some stale facts, but it misses older
still-current facts like SSO, escalation route, P2 SLA, and privacy policy.

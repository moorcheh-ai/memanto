# Policy Drift Memory Benchmark

This benchmark is a deterministic, offline evaluation for issue #639. It
stress-tests a common production memory failure mode: policy and customer facts
change over time, while older contradictory facts remain in the memory corpus.

The suite compares three isolated backends on the same event stream and golden
queries:

- `memanto_active_digest`: a Memanto-style active digest that keeps current
  state, supersedes stale facts, and avoids retrieving revoked sensitive facts.
- `append_only_log`: a passive baseline that retrieves every matching fact,
  including stale or revoked facts.
- `recent_window_log`: a cheap recent-window baseline that reduces tokens but
  forgets older still-current policy facts.

## Metrics

Each backend is scored on:

- retrieval accuracy against golden required and forbidden event IDs
- stale conflict rate
- sensitive leak rate
- average retrieved tokens
- stored tokens after ingestion
- deterministic p95 latency proxy

No network, LLM, Moorcheh API key, or external package is required for the
default run. The benchmark is intentionally adapter-shaped so the same dataset
can later be routed through a live Memanto/Moorcheh backend when credentials are
available.

## Run

```bash
python examples/benchmarks/policy-drift-memory/run_benchmark.py \
  --output examples/benchmarks/policy-drift-memory/results/sample_results.json \
  --markdown examples/benchmarks/policy-drift-memory/results/sample_results.md
```

## Test

```bash
python -m unittest discover -s examples/benchmarks/policy-drift-memory -p "test_*.py" -v
python -m py_compile examples/benchmarks/policy-drift-memory/run_benchmark.py \
  examples/benchmarks/policy-drift-memory/test_benchmark.py
```

## Dataset

The source dataset is in `data/policy_events.json`; the expected answers are in
`data/golden_queries.json`. The scenarios cover production log access, customer
support escalation, transcript retention, deployment windows, DPA scope,
release compliance, finance evaluation redaction, and regional processing.


# Support Escalation Memory Benchmark

This example adds a credential-free benchmark for issue #639. It models a long-running enterprise support escalation where durable facts change across handoffs:

- plan changes from starter to enterprise;
- region changes from eu-west to eu-central while us-east stays forbidden;
- SLA changes from 24 hours to 4 hours;
- owner changes from Alex to Priya;
- a beta API key is explicitly erased and must not be retrieved;
- severity and rollback details remain current.

The benchmark compares three retrieval strategies:

- `active_case_digest`: a Memanto-style compact current-state digest;
- `append_only_log`: retrieves every matching historical note, including stale facts;
- `recent_window_log`: keeps only recent notes and misses older durable constraints.

## Run

```bash
python3 run_benchmark.py
python3 -m unittest test_benchmark.py -q
```

The run writes:

- `results/sample_results.json`
- `results/sample_results.md`

## Why This Matters

Support and incident agents often fail by resurfacing stale state: old SLAs, prior owners, revoked secrets, or outdated data residency constraints. This benchmark measures current-fact accuracy, stale leak rate, token footprint, and retrieval latency without requiring API keys.

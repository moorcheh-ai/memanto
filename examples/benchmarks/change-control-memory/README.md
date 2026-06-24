# Change-Control Memory Benchmark

This benchmark evaluates whether an agent memory system can keep current operational facts while suppressing stale rollout notes, revoked approvals, and synthetic secrets.

It is designed for the Great Agentic Memory Showdown bounty (#639) as a credential-free, reproducible harness. The default run compares three local backends:

- `active_change_digest`: a compact current-state digest with evidence IDs and secret redaction
- `append_only_log`: a full history lookup that tends to surface stale facts
- `recent_window_log`: a small recency window that drops older still-current constraints

## What It Measures

- Current-fact retrieval accuracy
- Evidence citation coverage
- Stale-conflict rate
- Synthetic secret leak rate
- Retrieved token footprint
- P95 latency proxy
- Signal-to-noise ratio

## Run

```bash
python examples/benchmarks/change-control-memory/run_benchmark.py
python examples/benchmarks/change-control-memory/run_benchmark.py \
  --output examples/benchmarks/change-control-memory/results/sample_results.json \
  --markdown examples/benchmarks/change-control-memory/results/sample_results.md
python -m unittest discover -s examples/benchmarks/change-control-memory -p 'test_*.py'
```

No network, LLM, database, or API key is required.


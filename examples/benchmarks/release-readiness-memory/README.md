# Release Readiness Memory Benchmark

This benchmark models a long-lived coding agent that must hand off release facts after several sessions of changing instructions. It compares:

- `active_release_digest`: a Memanto-style current-fact digest by topic
- `append_only_log`: a naive memory log that retrieves every matching fact
- `recent_window_log`: a small recency window that can miss older current constraints

The dataset intentionally includes stale release instructions, a changed payment rail, deploy target changes, and a synthetic secret. The benchmark scores each backend on:

- retrieval accuracy against golden facts
- average retrieved token footprint
- p95 retrieval latency
- stale conflict rate
- synthetic secret leak rate

Run it without API keys:

```bash
python examples/benchmarks/release-readiness-memory/run_benchmark.py \
  --output examples/benchmarks/release-readiness-memory/results/sample_results.json \
  --markdown examples/benchmarks/release-readiness-memory/results/sample_results.md
```

Run tests:

```bash
python -m unittest discover -s examples/benchmarks/release-readiness-memory -p "test_*.py"
```

This is deliberately deterministic so maintainers can review the benchmark logic and sample metrics without needing a live `MOORCHEH_API_KEY`. A live Memanto adapter can be added later while keeping the same dataset and scoring contract.

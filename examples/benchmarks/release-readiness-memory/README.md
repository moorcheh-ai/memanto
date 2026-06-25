# Release Readiness Memory Benchmark

This benchmark models a long-lived coding agent that must hand off release facts after several sessions of changing instructions. It now includes a reproducible Memanto service backend instead of only mock strategy classes. The `memanto_service` run stores every event through `MemoryWriteService` as `MemoryRecord` objects and retrieves current memories through `MemoryReadService.search_memories` using a Moorcheh-compatible in-memory client.

- `memanto_service`: real Memanto write/read service path with active/superseded status filtering
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

This is deliberately deterministic so maintainers can review and rerun the benchmark without needing a live `MOORCHEH_API_KEY`, while still exercising Memanto's production record formatting, status metadata, and read/write service code paths.

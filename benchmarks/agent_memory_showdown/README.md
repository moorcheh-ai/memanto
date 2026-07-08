# Agent Memory Showdown Benchmark

This benchmark supports the Memanto issue #639 bounty by making the evaluation
reproducible before anyone runs paid cloud calls. It measures the same core
tension across adapters:

- retrieval accuracy against a golden dataset
- estimated tokens ingested and retrieved
- p95 retrieval latency

The default run uses two deterministic adapters:

- `stateful_compaction`: a local Memanto-shaped control that keeps current
  state and supersedes stale statements
- `append_only_keyword`: a vector-store-shaped control that appends every turn
  and retrieves by keyword overlap

These controls make CI stable and expose the measurement code. For a live
showdown, add an adapter that implements `MemoryAdapter` in `run_benchmark.py`
and run the same dataset against Memanto plus the competitor under identical
settings.

## Run

```bash
python benchmarks/agent_memory_showdown/run_benchmark.py \
  --dataset benchmarks/agent_memory_showdown/dataset.jsonl \
  --output-dir benchmark-results
```

The command writes:

- `benchmark-results/summary.json`
- `benchmark-results/results.csv`

## Method

Each JSONL row is one case with ordered memory turns and golden queries. The
runner ingests all turns into each adapter, asks the same queries, checks
expected and forbidden answer terms, and records:

- `ingested_tokens`: estimated by character count so every adapter is scored by
  the same tokenizer-independent heuristic
- `retrieved_tokens`: estimated from the adapter response
- `latency_ms`: measured around each retrieval call
- `accuracy`: fraction of query checks satisfied

The dataset intentionally includes stale preferences and ownership changes, so
append-only retrieval can surface obsolete facts while stateful memory should
prefer the current fact.


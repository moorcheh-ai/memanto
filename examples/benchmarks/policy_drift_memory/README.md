# Policy Drift Memory Benchmark

This benchmark stress-tests the core 2026 agent-memory tradeoff from issue
#639: retrieval accuracy versus resource footprint when instructions mutate
across sessions.

The dataset models support and operations agents that receive policy updates,
privacy reversals, launch-train changes, and escalation changes. The benchmark
then asks current-state questions where stale memories are actively harmful.

## Compared Backends

- `memanto_style_active_digest`: an offline Memanto-style typed digest that
  stores the current fact per key and returns compact current-state evidence.
- `episode_graph_baseline`: a graph-like episode memory baseline that groups
  values by key but keeps historical values in retrieval.
- `recent_window_3`: a recency-only baseline using the last three events for an
  entity.
- `append_only_log`: a passive memory baseline that replays every event for an
  entity.

The default suite is credential-free so reviewers can reproduce it without a
Moorcheh API key. It is intentionally structured so a live Memanto CLI adapter
can be added without changing the dataset or scoring contract.

## Metrics

- `accuracy`: fraction of queries that include all required current facts and no
  forbidden stale facts.
- `total_retrieved_tokens`: approximate token footprint returned to the agent
  across all benchmark queries.
- `avg_retrieved_tokens`: average retrieved context size per query.
- `p95_latency_ms`: p95 retrieval latency over repeated in-process retrievals.

## Run

```bash
python examples/benchmarks/policy_drift_memory/benchmark.py --repeats 200
```

Optional full detail output:

```bash
python examples/benchmarks/policy_drift_memory/benchmark.py \
  --repeats 200 \
  --output-json examples/benchmarks/policy_drift_memory/results.json
```

## Expected Shape

On the included dataset, the active digest should preserve current facts while
dropping stale instructions, so it should reach full accuracy with a much
smaller retrieval footprint than passive baselines. The exact latency values are
machine-dependent, but relative token footprint and stale-fact failures should
be stable.

Example output from a local run:

```text
backend,accuracy,total_retrieved_tokens,avg_retrieved_tokens,p95_latency_ms
memanto_style_active_digest,1.0,282,56.4,0.0168
episode_graph_baseline,0.4,261,52.2,0.0082
recent_window_3,0.0,315,63,0.0007
append_only_log,0.0,361,72.2,0.0004
```

## Reproducibility Notes

- Python 3.10 or newer.
- No third-party packages are required for the offline benchmark.
- The source dataset is `dataset.json`.
- Token counts are deterministic approximations based on word and punctuation
  boundaries, so they are comparable across backends without requiring a model
  tokenizer.
- The benchmark does not call external APIs by default.

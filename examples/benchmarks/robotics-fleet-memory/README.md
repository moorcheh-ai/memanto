# Robotics Fleet Memory Benchmark

This benchmark adds a deterministic, no-key evaluation harness for issue
[#639](https://github.com/moorcheh-ai/memanto/issues/639). It models a
warehouse robotics fleet where agents must remember the latest operating state
without resurfacing stale shift notes or a synthetic credential.

The scenario is intentionally different from generic support-chat memory tests:
fleet operations depend on corrected assignments, safety clearance, dock
reroutes, cold-chain policy changes, battery constraints, and dispatch owner
handoffs. A memory layer that returns every historical note can look
"complete" while still giving an unsafe answer.

## What It Measures

The harness runs the same event stream and golden queries through three memory
backends:

| Backend | Purpose |
| --- | --- |
| `append_only_log` | Passive baseline that returns all matching shift notes. |
| `recent_window` | Cheap recency baseline that drops older durable facts. |
| `active_fleet_digest` | Memanto-style active memory with overwrite semantics and sensitive-field suppression. |

For each backend the benchmark reports:

- Retrieval accuracy against the golden dataset.
- Total ingested tokens.
- Total and average retrieved tokens.
- p95 retrieval latency.
- Stale conflict rate.
- Secret leak rate.

## Run

Requires Node.js 20 or newer. No package install, API key, vector database, or
LLM call is required.

```bash
cd examples/benchmarks/robotics-fleet-memory
npm run benchmark
npm test
```

Equivalent direct commands:

```bash
node run_benchmark.mjs --output results/sample_results.json --markdown results/sample_results.md
node --test test_benchmark.mjs
```

`BENCHMARK_ITERATIONS` can be set to smooth latency percentiles:

```bash
BENCHMARK_ITERATIONS=200 node run_benchmark.mjs
```

## Dataset

The source dataset lives in
[`dataset/robotics_fleet_sessions.json`](dataset/robotics_fleet_sessions.json).
It contains 12 shift events and 7 golden queries:

- Current R-17 assignment after a stale aisle assignment.
- R-42 safety clearance after a lidar hold.
- Dock 3 reopening after a closure.
- Zone F cold-chain policy after a manual override is revoked.
- R-09 battery and firmware constraint.
- Dispatch owner handoff.
- Synthetic credential suppression.

## Sample Result

The committed sample result is generated with:

```bash
node run_benchmark.mjs --output results/sample_results.json --markdown results/sample_results.md
```

Expected shape:

| Backend | Expected behavior |
| --- | --- |
| `append_only_log` | Higher token usage with stale fact conflicts and credential leakage. |
| `recent_window` | Lower token usage but misses older durable state. |
| `active_fleet_digest` | High accuracy, lower retrieved tokens than append-only, zero credential leaks. |

## Live Adapter Path

`run_benchmark.mjs` keeps a small backend contract: `ingest(event)` and
`retrieve(query)`. That makes it straightforward to replace
`ActiveFleetDigestBackend` with a live Memanto adapter or to add Mem0/Zep
adapters while keeping the same dataset, metrics, and output format.

## Public Showcase

This PR is the technical showcase for the benchmark and includes reproducible
commands plus committed result artifacts. External social analytics are not
fabricated in this repository.
